from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Run from the repository after npm ci && npm run build in web/.
# No user homes, runtime data, model weights or credentials are collected.
root = Path(SPECPATH).parent
analysis = Analysis([str(root / 'deploy' / 'standalone-entry.py')], pathex=[str(root)],
    binaries=[], datas=collect_data_files('alterecho'),
    hiddenimports=collect_submodules('uvicorn') + collect_submodules('fastapi') + collect_submodules('pydantic'),
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas, [], name='alterecho',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
