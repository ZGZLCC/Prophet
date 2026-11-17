from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


ROOT = Path(SPECPATH)
datas = collect_data_files("izthon", includes=["i18n/_catalogs/*.json"])
binaries = []
hiddenimports = [
    "izthon.astro.astro",
    "izthon.star.adjective_star",
    "izthon.star.decorative_star",
    "izthon.star.horoscope_star",
    "izthon.star.location",
    "izthon.star.major_star",
    "izthon.star.minor_star",
]

datas += [
    (str(ROOT / ".env.example"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE.md"), "."),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "web"), "web"),
    (str(ROOT / "exporters"), "exporters"),
    (str(ROOT / "chat-material-extractor"), "chat-material-extractor"),
    (str(ROOT / "fortune" / "data"), "fortune/data"),
    (str(ROOT / "fortune" / "schemas"), "fortune/schemas"),
]
hiddenimports += [
    "api",
    "api.base",
    "api.chat",
    "api.dialogs",
    "api.fortune",
    "api.profile",
    "api.settings",
    "analysis",
    "app_api",
    "background_jobs",
    "chat_analysis",
    "chat_export",
    "fortune",
    "fortune.engines",
    "fortune.knowledge",
    "fortune.storage",
    "fortune_app",
    "parsers",
    "person_profile",
    "person_profile.analysis",
    "person_profile.export",
    "person_profile.parsers",
    "person_profile.storage",
    "process_runner",
    "profile_export",
    "storage",
    "winreg",
]

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "anyio", "distro", "httpcore", "httpx", "jiter", "openai", "pydantic",
        "pydantic_core", "sniffio", "numpy", "pandas", "pyarrow", "PIL",
        "matplotlib", "scipy", "lxml.builder", "lxml.html", "lxml.isoschematron",
        "lxml.objectify", "lxml.sax",
    ],
    noarchive=False,
)
a.datas = [
    item for item in a.datas
    if not item[0].replace("\\", "/").startswith("lxml/isoschematron/")
    and item[0].replace("\\", "/") != "pythonnet/runtime/Python.Runtime.xml"
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Prophet",
    icon=str(ROOT / "assets" / "prophet_icon_light.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Prophet",
)
