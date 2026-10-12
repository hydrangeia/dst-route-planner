# Working on DST Route Planner

- Read `README.md` / `README.en.md` and `TODO.md` before choosing the next milestone.
- Keep Chinese and English README content in sync, including supported features and limitations.
- This repository currently implements an external Python mainland inference prototype. Do not describe it as an installed in-game mod or a spatial world-generation simulator.
- Use available local DST source definitions to verify generation rules; record source paths relative to the DST scripts directory. Tests must run without those external game files.
- For independent subtasks, use multiple agents when useful. The owner's preferred worker configuration is `gpt-6-luna` with reasoning effort `max`; honor a different explicit request for a particular task.
- Assign each worker specific files. Workers share the checkout and must preserve and accommodate others' edits.
- Run meaningful regression checks with `python -m pytest -q` and affected CLI examples. Add tests for knowledge integrity and sampler behavior when changing these areas.
- Keep secrets, local environments, caches, personal notebooks, and game source archives out of Git commits. Use a GitHub noreply address for public commits.
- Update `TODO.md` when a milestone is completed. Do not claim real-world accuracy without an evaluation dataset.
