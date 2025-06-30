import configparser
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Config:
    protected_columns: List[str]
    dropdown_values: Dict[str, List[str]]
    required_columns: List[str]
    base_save_path: str
    parent_child_map: Dict[str, List[str]]
    excel_autoload_path: str
    excel_template_path: str

def _safe_get(cfg, sect, opt, default=""):
    try:
        return cfg.get(sect, opt)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return default

def load_config(path: str = "config.ini") -> Config:
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    cfg.read(path)

    protected_columns = [c.strip() for c in _safe_get(cfg, "PROTECTED_COLUMNS", "columns").split(",") if c]
    required_columns = [c.strip() for c in _safe_get(cfg, "REQUIRED_COLUMNS", "columns").split(",") if c]

    dropdown_values = {}
    if cfg.has_section("DROPDOWN_VALUES"):
        for k in cfg["DROPDOWN_VALUES"]:
            dropdown_values[k] = [x.strip() for x in cfg.get("DROPDOWN_VALUES", k).split(",")]

    parent_child_map = {}
    if cfg.has_section("PARENT_CHILD_RELATIONS"):
        for k in cfg["PARENT_CHILD_RELATIONS"]:
            parent_child_map[k] = [x.strip() for x in cfg.get("PARENT_CHILD_RELATIONS", k).split(",")]

    return Config(
        protected_columns,
        dropdown_values,
        required_columns,
        _safe_get(cfg, "GENERAL", "base_save_path", "output"),
        parent_child_map,
        _safe_get(cfg, "GENERAL", "excel_autoload_path", ""),
        _safe_get(cfg, "GENERAL", "excel_template_path", "test.xlsx")
    )

def load_excel_template_columns(path: str) -> List[str]:
    import os
    import pandas as pd

    if os.path.exists(path):
        try:
            return pd.read_excel(path, engine="openpyxl").columns.tolist()
        except Exception:
            pass
    return []
