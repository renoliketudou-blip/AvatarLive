"""AvatarLive M0 self-test #2: config loads + all referenced handler modules resolve."""
import sys
import importlib

sys.path.insert(0, "src")
sys.path.insert(0, ".")  # project root -> top-level `src` package importable

from chat_engine.data_models.chat_engine_config_data import ChatEngineConfigModel
from service.service_utils.service_config_loader import load_configs


class _Args:
    env = "default"
    config = "config/chat_with_openai_compatible_bailian_cosyvoice_flashhead.yaml"


_logger_cfg, _service_cfg, cfg = load_configs(_Args())
print("✅ config loads OK; handler_configs:", list(cfg.handler_configs.keys()))

# Resolve every handler module referenced by the config
mods = []
for name, hc in cfg.handler_configs.items():
    mod = hc.get("module") if isinstance(hc, dict) else getattr(hc, "module", None)
    if not mod:
        continue
    try:
        # modules are declared relative to handler_search_path (src/handlers)
        importlib.import_module("handlers." + mod.replace("/", "."))
        mods.append(f"OK  {name}:{mod}")
    except Exception as e:
        mods.append(f"FAIL {name}:{mod} -> {type(e).__name__}: {e}")

for m in mods:
    print("  " + m)

failed = [m for m in mods if m.startswith("FAIL")]
if failed:
    print("❌", len(failed), "handler modules FAILED to import")
    sys.exit(1)
print("✅ all", len(mods), "handler modules imported")
