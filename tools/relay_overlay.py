#!/usr/bin/env python3
"""把 gate-probe 交接資料夾裡「套用後的完整檔案」覆寫到中繼 repo 的乾淨複本，前後都核對 SHA-256。

用法：python3 relay_overlay.py <MANIFEST.tsv> <gate-probe repo 根目錄> <中繼 repo 根目錄>

MANIFEST.tsv 欄位（tab 分隔、第一列是標題）：
  relay_path  gate_probe_path  base_sha256  patched_sha256
base_sha256 為 "(new file)" 表示中繼原本沒有這個檔案。
任何一個雜湊不符就結束碼 1，不覆寫後面的檔案（已覆寫的不還原；這個工具只用在用完即丟的複本）。
"""
import hashlib
import shutil
import sys
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(manifest, probe_root, relay_root):
    probe_root, relay_root = Path(probe_root), Path(relay_root)
    rows = [line.rstrip("\n").split("\t") for line in Path(manifest).read_text(encoding="utf-8").splitlines()]
    header, rows = rows[0], [r for r in rows[1:] if any(r)]
    if header != ["relay_path", "gate_probe_path", "base_sha256", "patched_sha256"]:
        print(f"MANIFEST 標題不符：{header}")
        return 1
    for relay_path, probe_path, base, patched in rows:
        target, source = relay_root / relay_path, probe_root / probe_path
        if base == "(new file)":
            if target.exists():
                print(f"FAIL {relay_path}: 應為新檔案，但中繼已有此檔")
                return 1
            base_state = "new"
        else:
            if not target.is_file():
                print(f"FAIL {relay_path}: 中繼沒有此檔")
                return 1
            got = sha256(target)
            if got != base:
                print(f"FAIL {relay_path}: 原檔 SHA-256 {got} ≠ MANIFEST {base}（中繼已改過，修補需重做）")
                return 1
            base_state = "base-ok"
        if sha256(source) != patched:
            print(f"FAIL {probe_path}: 交接檔 SHA-256 ≠ MANIFEST {patched}")
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha256(target) != patched:
            print(f"FAIL {relay_path}: 覆寫後 SHA-256 不符")
            return 1
        print(f"OK   {relay_path}  {base_state}  -> {patched}")
    print(f"overlay done: {len(rows)} files")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))
