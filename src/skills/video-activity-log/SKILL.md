---
name: video-activity-log
description: Generate an Obsidian-flavored Markdown activity log from a screen-recording video (typically a bub-eye segment). Use when the user provides a path to an .mp4/.mov screen capture and asks to summarize, journal, describe, or log what the user was doing on screen — including variants like "写一份活动日志", "总结这段录屏", "看看这个视频我做了什么", or "analyze this screen recording". Produces time-ranged bullets with `[[wikilinks]]` on key entities (apps / sites / people / projects) and records any browsing URL visible on screen, so the log is retrievable and linkable inside an Obsidian vault. Includes an ffmpeg-based idle preflight that short-circuits LLM calls on segments that are mostly locked screen / screensaver.
---

# Video Activity Log

Turn a screen-recording video into a compact Obsidian journal entry that is (a) linkable via `[[wikilinks]]` and (b) retrievable — a future reader should be able to skim the log and know roughly where to seek in the video.

This is a **three-phase** skill:

- **Phase 0** — ffmpeg preflight short-circuits idle segments without touching the LLM.
- **Phase 1** — the LLM watches the video and writes a draft with *relative* time ranges.
- **Phase 2** — a Python script shifts ranges to absolute wall-clock time, fills the frontmatter, and warns on bullet-quality issues.

Do not do time arithmetic in your head — always hand that off to Phase 2.

## Inputs

- **Video path** (required): absolute path to a screen-recording file. `bub-eye` produces `eye_YYYYMMDD_HHMMSS.mp4` under `~/.bub/eye/segments/`; the filename's timestamp is the wall-clock start of the segment.
- **Output path** (optional): where to write the final `.md`. Default: sibling of the video, same basename, `.md` extension.

## Workflow

### Phase 0 — Idle preflight

```bash
uv run ${SKILL_DIR}/scripts/preflight_idle.py --video <path> [--output <md-path>]
```

Exit codes:
- **0** — segment was idle; a one-line `#idle` log was written. Task done; report to user.
- **1** — segment had activity; proceed to Phase 1.
- **2** — environment error (`ffmpeg` / `ffprobe` missing, video unreadable). Fix and retry.

Tuning (rarely needed): `--idle-scene-rate 0.01` (max scene-changes per second to count as idle), `--idle-min-seconds 60` (skip classification for shorter clips), `--scene-sensitivity 0.01` (ffmpeg scene filter threshold). `--dry-run` prints the verdict without writing.

### Phase 1 — Watch the video, write a draft with *relative* times

1. **Pass the video to the model directly.** The underlying LLM supports native video understanding — do not extract frames, transcode, or OCR. Provide the file path and the rules below.
2. **Emit time ranges as offsets from the video start**, always in backticks. Use `MM:SS - MM:SS` for segments under an hour, `HH:MM:SS - HH:MM:SS` otherwise. The first bullet typically starts at `00:00` or slightly after. **Do not attempt to produce wall-clock times** — the script does that in Phase 2.
3. **Segment by activity, not by clock.** One bullet per coherent activity — an app-level switch, a topic change in the same app, or a clear pause. Do not force a fixed cadence.
4. **Default to merging — see the rules below.** Over-splitting is the #1 failure mode.
5. **Write `[[wikilinks]]` on retrievable anchors, not on prose.** Wrap proper nouns and things the user would later want to link / search: sites (by hostname — see naming rule), desktop apps, people, projects / repos, documents, channels, technical concepts that recur. Do not wrap generic verbs or filler ("看", "写", "讨论").
6. **Capture URLs when visible.** If the browser's address bar or tab title exposes a URL, include it verbatim in backticks inside the bullet — e.g. ``浏览 `https://github.com/bubbuild/bub-eye/pull/42` ``. Prefer the full URL over the domain.
7. **Keep it skimmable.** One line per segment, roughly 15–30 Chinese characters (or 10–20 English words) of body after the time range. Enough to recognize the moment and seek back into the video; not a transcript.
8. **Do not invent.** If a name, URL, or topic is not actually legible, omit it. A vague bullet (`在 [[chrome]] 浏览未知标签页`) beats a fabricated one.

#### 合并优先 (Default to Merging)

Over-splitting is far worse than under-splitting — carpet-bombed micro-bullets are unusable, a merged bullet is still retrievable. When in doubt, **merge**.

- **≲ 30 s 的快速切换视为干扰项**，并入相邻 bullet；don't give them their own line.
- **同一工作流里的应用反复切换** (VS Code → Terminal → VS Code，或 IDE ↔ 浏览器查文档) = 1 条 bullet，不要拆成 3 条。把次要应用放在描述里（"期间在 X / Y 短暂打断"）。
- **同一主题跨应用** (微信聊 A 项目 → 看 A 项目 PR → 打开 A 项目 IDE) 优先按主题合并。
- **相邻 bullet 间隔 ≥ 60 s 的空白会被 Phase 2 标记为 `gap`**。如果真实发生了空白（离座、吃饭），用一条覆盖该段的 bullet 明确记录（例如 `离席` 或 `未在屏幕前`），而不是留空。
- **单条 bullet 最短 30 s**。更短的会被 Phase 2 标记为 `short`；合并进相邻 bullet。

#### 好坏对比

```
❌ `13:05 - 13:07` 在 [[Chrome]] 浏览
✅ `13:05 - 13:07` 在 [[trac.ffmpeg.org]] 查阅 [[HEVC]] 关键帧设置

❌ `13:20 - 13:22` 调 bug
✅ `13:20 - 13:22` 定位 [[bub-eye]] segment 不轮转的 ffmpeg 参数

❌ `13:30 - 13:31` 在 [[微信]] 聊天
✅ `13:30 - 13:31` 在 [[微信]] 和 [[chenkai]] 讨论 [[bub-eye]] v2 roadmap

❌ 把 `13:40 - 13:41` 刷 Twitter / `13:41 - 13:43` 回 Slack / `13:43 - 13:55` 改代码 拆成 3 条
✅ `13:40 - 13:55` 在 [[VS Code]] 改代码，期间在 [[twitter.com]] / [[Slack]] 短暂打断
```

#### 应用 vs. 站点的命名

- **浏览器内的活动** → 用 URL 的 hostname 做 wikilink，去掉 `www.` 前缀，保留子域。例：`[[figma.com]]`、`[[docs.google.com]]`、`[[github.com]]`、`[[mail.google.com]]`、`[[trac.ffmpeg.org]]`。完整 URL 仍可在反引号里单独记。
- **桌面原生 / 移动应用** → 用应用名。例：`[[VS Code]]`、`[[微信]]`、`[[Terminal]]`、`[[Figma]]`（桌面版区别于 `[[figma.com]]`）。
- **判断准则**：活动发生在"浏览器里某个站点"就用域名；在"独立应用进程"里就用应用名。
- 理由：Obsidian vault 里 `[[figma.com]]` 能沉淀一条站点维度的笔记（跨项目聚合访问），而 `[[Figma]]` 会把桌面版和 Web 版混在一起，检索价值低。

#### Draft format

Write the draft to a temp file (e.g. `/tmp/<video-basename>.draft.md`). The frontmatter block is required — the script rewrites it — but its values can be placeholders:

````markdown
---
video: PLACEHOLDER
date: PLACEHOLDER
start: PLACEHOLDER
end: PLACEHOLDER
---

# 活动日志

- `00:12 - 04:58` 在 [[VS Code]] 编辑 [[bub-eye]] 的 `segment_rotator.py`，调整关键帧间隔参数
- `05:00 - 06:02` 在 [[微信]] 和 [[chenkai]] 对话，讨论 [[bub-eye]] 项目的进展
- `06:10 - 09:44` 在 [[trac.ffmpeg.org]] 查阅 `https://trac.ffmpeg.org/wiki/Encode/H.265`，关于 [[HEVC]] 关键帧设置
- ...

## 关键实体

- 人：[[chenkai]]
- 项目：[[bub-eye]]
- 应用 (桌面)：[[VS Code]], [[微信]]
- 站点 (Web)：[[trac.ffmpeg.org]]
- 主题：[[HEVC]]
````

Conventions:
- Default to Chinese prose in bullets. Keep proper nouns in their original script (`[[bub-eye]]`, `[[VS Code]]`).
- The trailing `关键实体` section is a deduplicated roll-up of every `[[wikilink]]` used above, grouped by category. Keep two separate lines: **应用 (桌面)** for native apps and **站点 (Web)** for hostnames — don't mix them. Omit any category with no entries.
- The H1 stays as plain `# 活动日志` in the draft. Phase 2 does **not** rewrite the H1 — if the user wants the Daily-Note-backlink H1 (`# [[YYYY-MM-DD]] 活动日志`), include the `[[date]]` in the draft and it will pass through untouched.

### Phase 2 — Run the finalizer

```bash
uv run ${SKILL_DIR}/scripts/finalize_log.py \
  --video <video-path> \
  --draft <draft-path> \
  [--output <output-path>] \
  [--base-time YYYY-MM-DDTHH:MM:SS] \
  [--min-bullet-seconds 30] \
  [--max-gap-seconds 60] \
  [--no-validate]
```

What it does:
- Parses the wall-clock start from the video filename (`eye_YYYYMMDD_HHMMSS.mp4`), or takes `--base-time` as an override.
- Rewrites every `` `MM:SS - MM:SS` `` / `` `HH:MM:SS - HH:MM:SS` `` backtick span in the draft to absolute `HH:MM:SS`.
- Replaces the frontmatter with `video` (absolute path), `date`, `start` (earliest bullet), `end` (latest bullet).
- Validates bullet quality and prints any issues to stderr (non-blocking — the file is still written).
- Writes the finalized file to `--output` (default: `<video>.md`).

Validation categories (warn-only):
- **`gap`** — neighbouring bullets leave more than `--max-gap-seconds` between them.
- **`short`** — a bullet is shorter than `--min-bullet-seconds` (last bullet is exempt; it may be truncated by segment end).
- **`head`** — the first bullet starts more than `--max-gap-seconds` after the video start.
- **`tail`** — the last bullet ends more than `--max-gap-seconds` before the video end (requires `ffprobe`).

If validation complains, inspect the stderr list and decide whether to re-prompt the LLM with targeted feedback (e.g. "merge the 10s bullets" or "cover the 13:09 – 13:12 gap"). Use `--no-validate` to silence the check when you know the draft is intentionally sparse.

Example:
```bash
uv run ${SKILL_DIR}/scripts/finalize_log.py \
  --video ~/.bub/eye/segments/eye_20260417_130000.mp4 \
  --draft /tmp/eye_20260417_130000.draft.md
# → writes ~/.bub/eye/segments/eye_20260417_130000.md
# → stderr: "span: 13:00:12 - 13:14:55" then any validation issues
```

If the filename has no `eye_YYYYMMDD_HHMMSS` pattern (e.g. an unrelated `.mp4`), pass `--base-time` explicitly and the script shifts times from that anchor.

## Reporting back to the user

After Phase 0 (idle) or Phase 2 (finalize) finishes, reply with:
- the output path,
- the wall-clock span covered (stderr: `span: ...`),
- any Phase 2 validation issues (stderr) if they fired — surface them so the user can decide whether to re-prompt,
- 3–5 highlight bullets copied verbatim from the final file so the user can judge quality without opening it.
