# 情绪调节表情样例图

情绪调节编辑器左侧的表情样例图放在本目录，命名为 `<key>.png`（建议正方形或 4:3，
灰模/素模风格，参考 libtv）。图片未就绪时 UI 显示占位底图，不影响功能。

网格位置（行 0 = 最激动/顶部，列 0 = 最亲近/左侧）→ 文件名：

| 行\列 | 0 亲近 | 1 | 2 | 3 | 4 疏离 |
|---|---|---|---|---|---|
| 0 激动 | ecstatic.png 狂喜 | excited.png 兴奋 | surprised-joy.png 惊喜 | astonished.png 惊愕 | furious.png 暴怒 |
| 1 | passionate.png 热情 | joyful.png 喜悦 | surprised.png 惊讶 | anxious.png 焦虑 | angry.png 愤怒 |
| 2 | affectionate.png 亲昵 | smiling.png 微笑 | neutral.png 平和 | vigilant.png 警觉审视 | indifferent.png 冷漠 |
| 3 | tender.png 温柔 | content.png 满足 | relaxed.png 放松 | doubtful.png 疑虑 | disdainful.png 轻蔑 |
| 4 平静 | devoted.png 依恋 | serene.png 安宁 | tranquil.png 沉静 | melancholy.png 忧郁 | detached.png 疏离 |

对应关系定义在 `src/features/canvas/domain/emotionAdjust.ts`（EMOTION_GRID），改名/换文案在那里同步。
