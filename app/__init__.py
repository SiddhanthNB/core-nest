import os

# use litellm's bundled model cost map instead of fetching it over the network at import
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
