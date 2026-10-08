import pkgutil
import importlib

__all__ = []

for loader, module_name, is_pkg in pkgutil.iter_modules(__path__):
    module = importlib.import_module(f"{__name__}.{module_name}")
    for attr in dir(module):
        if attr.startswith("fetch_"):
            globals()[attr] = getattr(module, attr)
            __all__.append(attr)
