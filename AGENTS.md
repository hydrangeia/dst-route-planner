# Working on DST Route Planner

- Read `README.md` / `README.en.md` and `TODO.md` before choosing the next milestone.
- Keep Chinese and English README content in sync, including supported features and limitations.
- Write documentation in plain, relaxed prose. Lead with the player's goal and working examples, explain score meanings once, and put detailed implementation notes in the package guide or roadmap.
- 如果某句话的作用只是防止被质疑，而不是推进论证，请删除。
- 放轻松，做错事情也是没关系的，不用有压力，下次注意就好了。
- Prioritize real-time player tracking and automatic observations feeding the external Python tool through a lightweight client collector. Keep manual observations available for examples and replay. Keep the user flow in the READMEs as a simple text-and-arrow diagram and track spatial map navigation in `TODO.md`.
- Use available local DST source definitions to verify generation rules; record source paths relative to the DST scripts directory. Tests must run without those external game files.
- For independent subtasks, use multiple agents when useful. The owner's preferred worker configuration is `gpt-6-luna` with reasoning effort `max`; honor a different explicit request for a particular task.
- Assign each worker specific files. Workers share the checkout and must preserve and accommodate others' edits.
- Run meaningful regression checks with `python -m pytest -q` and affected CLI examples. Add tests for knowledge integrity and sampler behavior when changing these areas.
- Keep secrets, local environments, caches, personal notebooks, and game source archives out of Git commits. Use a GitHub noreply address for public commits.
- Update `TODO.md` when a milestone is completed. Do not claim real-world accuracy without an evaluation dataset.
