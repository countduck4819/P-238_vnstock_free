import pkgutil
import importlib

blueprints = []

for loader, module_name, is_pkg in pkgutil.iter_modules(__path__):
    module = importlib.import_module(f"{__name__}.{module_name}")
    for attr in dir(module):
        if attr.endswith("_bp"):  # chỉ lấy các biến blueprint
            blueprints.append(getattr(module, attr))

__all__ = ["blueprints"]
