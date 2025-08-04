import argparse
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple, Union, List
import concurrent.futures as cf

import numpy as np
from PIL import Image
import pydicom
from pydicom.pixel_data_handlers.util import apply_modality_lut, apply_voi_lut
from tqdm import tqdm

# --------------------------
# Helpers
# --------------------------

PATIENT_ID_RE = re.compile(r"(\d{3}_S_\d{4,})")

def find_patient_id_from_path(path: Path) -> Optional[str]:
    for part in path.parts:
        m = PATIENT_ID_RE.search(part)
        if m:
            return m.group(1)
    return None

def sanitize(name: str, max_len: int = 120) -> str:
    if name is None:
        return "unknown"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", str(name))
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len] if len(name) > max_len else name

def get_datestr(ds: pydicom.dataset.FileDataset) -> str:
    if "AcquisitionDateTime" in ds:
        dt = str(ds.AcquisitionDateTime)
        return dt[:14] if len(dt) >= 14 else dt
    date = str(ds.get("AcquisitionDate", "")) or str(ds.get("StudyDate", ""))
    time = str(ds.get("AcquisitionTime", ""))
    if date and time:
        return f"{date}_{time[:6]}" if len(time) >= 6 else f"{date}_{time}"
    if date:
        return date
    return "unknown_date"

def auto_window(arr: np.ndarray, low_pct: float = 1.0, high_pct: float = 99.0) -> Tuple[float, float]:
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return float(np.nanmin(arr)), float(np.nanmax(arr))
    lo = np.percentile(finite, low_pct)
    hi = np.percentile(finite, high_pct)
    if hi <= lo:
        lo, hi = float(np.min(finite)), float(np.max(finite))
    return float(lo), float(hi)

def to_uint8(arr: np.ndarray, ds: Optional[pydicom.dataset.FileDataset]) -> np.ndarray:
    original = arr
    try:
        arr = apply_modality_lut(arr, ds) if ds is not None else arr
    except Exception:
        arr = original

    try:
        arr = apply_voi_lut(arr, ds) if ds is not None else arr
        if arr.dtype.kind in "ui" and (np.max(arr) > 255 or np.min(arr) < 0):
            lo, hi = auto_window(arr)
            arr = np.clip((arr - lo) / (hi - lo + 1e-8), 0, 1.0) * 255.0
        else:
            lo, hi = auto_window(arr)
            arr = np.clip((arr - lo) / (hi - lo + 1e-8), 0, 1.0) * 255.0
    except Exception:
        lo, hi = auto_window(arr)
        arr = np.clip((arr - lo) / (hi - lo + 1e-8), 0, 1.0) * 255.0

    arr = np.nan_to_num(arr, nan=0.0, posinf=255.0, neginf=0.0)
    arr = np.clip(arr, 0, 255).astype(np.uint8)

    photometric = (ds.get("PhotometricInterpretation") if ds is not None else None) or ""
    if photometric.upper().strip() == "MONOCHROME1":
        arr = 255 - arr
    return arr

def save_image(arr: np.ndarray, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if arr.ndim == 2:
        im = Image.fromarray(arr, mode="L")
    elif arr.ndim == 3 and arr.shape[-1] == 3:
        im = Image.fromarray(arr, mode="RGB")
    else:
        if arr.ndim == 3:
            arr = arr[:, :, 0]
        im = Image.fromarray(arr.astype(np.uint8), mode="L")
    im.save(out_path, format="JPEG", quality=95, subsampling=0, optimize=True)

def build_output_path(
    out_root: Path,
    patient_id: str,
    ds: pydicom.dataset.FileDataset,
    instance_number: Optional[int],
    frame_index: Optional[int] = None,
) -> Path:
    series_desc = sanitize(ds.get("SeriesDescription", "")) or f"Series_{sanitize(ds.get('SeriesInstanceUID','unknown'))}"
    date_str = sanitize(get_datestr(ds))
    if instance_number is not None:
        base_name = f"{instance_number:06d}"
    else:
        base_name = sanitize(ds.get("SOPInstanceUID", "instance"))
    if frame_index is not None:
        base_name = f"{base_name}_f{frame_index:04d}"
    filename = f"{base_name}.jpg"
    return out_root / patient_id / series_desc / date_str / filename

def convert_one_dicom(dcm_path: Union[str, Path], out_root: Union[str, Path], default_patient_from_tree: bool = True):
    """
    Worker-safe: takes simple types, returns (ok: bool, err: Optional[str])
    """
    dcm_path = Path(dcm_path)
    out_root = Path(out_root)
    try:
        ds = pydicom.dcmread(dcm_path, force=True)

        patient_id = find_patient_id_from_path(dcm_path)
        if not patient_id:
            for tag in ("PatientID", "PatientName"):
                val = ds.get(tag)
                if val:
                    m = PATIENT_ID_RE.search(str(val))
                    if m:
                        patient_id = m.group(1)
                        break
        if not patient_id and default_patient_from_tree:
            patient_id = sanitize(dcm_path.parent.parent.name)
        if not patient_id:
            patient_id = "unknown_patient"

        arr = ds.pixel_array  # decompression may be CPU-bound
        saved = 0

        if arr.ndim == 3 and arr.shape[-1] == 3 and ds.get("SamplesPerPixel") == 3:
            if arr.dtype != np.uint8 or arr.min() < 0 or arr.max() > 255:
                lo, hi = auto_window(arr.astype(np.float32))
                arr = np.clip((arr - lo) / (hi - lo + 1e-8), 0, 1.0) * 255.0
                arr = arr.astype(np.uint8)
            out_path = build_output_path(out_root, patient_id, ds, int(ds.get("InstanceNumber", 0)) if ds.get("InstanceNumber") else None)
            save_image(arr, out_path)
            saved += 1

        elif arr.ndim == 3 and arr.shape[0] > 1 and (arr.shape[-1] != 3 or ds.get("SamplesPerPixel") != 3):
            for i in range(arr.shape[0]):
                frame = arr[i]
                frame_u8 = to_uint8(frame, ds)
                out_path = build_output_path(
                    out_root, patient_id, ds,
                    int(ds.get("InstanceNumber", 0)) if ds.get("InstanceNumber") else None,
                    frame_index=i
                )
                save_image(frame_u8, out_path)
                saved += 1

        else:
            arr_u8 = to_uint8(arr, ds)
            out_path = build_output_path(
                out_root, patient_id, ds,
                int(ds.get("InstanceNumber", 0)) if ds.get("InstanceNumber") else None
            )
            save_image(arr_u8, out_path)
            saved += 1

        return True, None if saved > 0 else "No frames saved"

    except Exception as e:
        return False, f"{dcm_path}: {e}"

def scan_for_dicoms(root: Union[str, Path]) -> List[Path]:
    root = Path(root)
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".dcm"]

# --------------------------
# Parallel helpers
# --------------------------

def parallel_convert(files: List[Path], out_root: Path, workers: int, executor_type: str = "process") -> List[str]:
    """
    Convert a list of DICOM paths in parallel.
    Returns a list of error messages (empty on success).
    """
    if not files:
        return []

    failures: List[str] = []
    Executor = cf.ProcessPoolExecutor if executor_type == "process" else cf.ThreadPoolExecutor

    # On heavy decompression, processes perform better.
    with Executor(max_workers=workers) as ex:
        futures = [ex.submit(convert_one_dicom, str(p), str(out_root)) for p in files]
        for fut in tqdm(cf.as_completed(futures), total=len(futures), desc=f"Converting ({executor_type})"):
            try:
                ok, err = fut.result()
                if not ok and err:
                    failures.append(err)
            except Exception as e:
                failures.append(str(e))
    return failures

# --------------------------
# Main
# --------------------------

def main(
    mri_root: Union[str, Path],
    pet_root: Union[str, Path],
    mri_out_root: Union[str, Path],
    pet_out_root: Union[str, Path],
    workers: int,
    executor_type: str,
) -> None:
    mri_root = Path(mri_root)
    pet_root = Path(pet_root)
    mri_out_root = Path(mri_out_root)
    pet_out_root = Path(pet_out_root)

    logging.info("Scanning for MRI DICOMs under %s", mri_root)
    mri_files = scan_for_dicoms(mri_root) if mri_root.exists() else []
    logging.info("Found %d MRI DICOM(s).", len(mri_files))

    logging.info("Scanning for PET DICOMs under %s", pet_root)
    pet_files = scan_for_dicoms(pet_root) if pet_root.exists() else []
    logging.info("Found %d PET DICOM(s).", len(pet_files))

    total = len(mri_files) + len(pet_files)
    if total == 0:
        logging.warning("No DICOM files found. Check your input paths.")
        return

    # MRI
    mri_failures = parallel_convert(mri_files, mri_out_root, workers=workers, executor_type=executor_type)

    # PET
    pet_failures = parallel_convert(pet_files, pet_out_root, workers=workers, executor_type=executor_type)

    failures = mri_failures + pet_failures
    if failures:
        logging.warning("Completed with %d failure(s). Showing first 10:", len(failures))
        for line in failures[:10]:
            logging.warning("  %s", line)
    else:
        logging.info("All files converted successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert DICOM (.dcm) MRI and PET images to JPEG, in parallel.")
    parser.add_argument("--mri-root", type=Path, default=Path(r"E:\inputs\Images"),
                        help="Root folder containing MRI DICOMs (default: E:\\inputs\\Images)")
    parser.add_argument("--pet-root", type=Path, default=Path(r"E:\inputs\PET"),
                        help="Root folder containing PET DICOMs (default: E:\\inputs\\PET)")
    parser.add_argument("--mri-out", type=Path, default=Path(r"E:\inputs\Updated"),
                        help="Output root for MRI JPGs (default: E:\\inputs\\Updated)")
    parser.add_argument("--pet-out", type=Path, default=Path(r"E:\inputs\Updated_PET"),
                        help="Output root for PET JPGs (default: E:\\inputs\\Updated_PET)")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                        help="Number of parallel workers (default: CPU count - 1)")
    parser.add_argument("--executor", choices=["process", "thread"], default="process",
                        help="Use process- or thread-based parallelism (default: process)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # a = 'D:\\Programming\\Python\\ADNI-Knowledge-Graph\\inputs\\Images'
    # b = 'D:\\Programming\\Python\\ADNI-Knowledge-Graph\\inputs\\PET'
    # c = 'D:\\Programming\\Python\\ADNI-Knowledge-Graph\\inputs\\Updated'
    # d = 'D:\\Programming\\Python\\ADNI-Knowledge-Graph\\inputs\\Updated_PET'

    main(args.mri_root, args.pet_root, args.mri_out, args.pet_out, workers=args.workers, executor_type=args.executor)
    # main(a, b, c, d, workers=args.workers, executor_type=args.executor)
