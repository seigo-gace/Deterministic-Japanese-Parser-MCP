# Dictionaries

`system/` contains versioned defaults shipped by the project. Large standard data is split into reviewable files: `metaphors/*.json` by domain-sized group and `rules/*.yaml` by intent. `user/` contains local override files and starts empty.

No tool may merge generated proposals into `system/` automatically. Run `tools/validator.py` after any edit.
