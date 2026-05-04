# 微信消息处理规则

> 本文件定义了微信机器人的消息路由规则。
> 如需修改路由逻辑，请编辑本文件后同步到 `wechat_bot.py` 中的 `parse_and_route()` 函数。

---

## 一、路由总览

| 内容特征 | 路由结果 | 处理方式 |
|---------|---------|---------|
| 豆瓣电影/剧集链接 | `douban_movie:{id}` | 调用 `douban_bot.py add movie {id}` |
| 豆瓣图书链接 | `douban_book:{id}` | 调用 `douban_bot.py add book {id}` |
| 包含"待办/TODO/记得/要做" | `ima_todo` | 存入 IMA 待办 |
| 包含"感想/想法/感悟/思考/启发/我觉得" | `ima_note` | 存入 IMA 感想笔记 |
| 任意 HTTP/HTTPS 链接（不含豆瓣） | `llm_wiki` | 摄入 LLM Wiki |
| 其他所有内容 | `ima_inbox` | 存入 IMA 通用收集箱 |

---

## 二、规则详情

### 规则 1：豆瓣电影/剧集链接

**触发条件：** 消息包含以下 URL 格式之一
```
douban.com/subject/{数字}
movie.douban.com/subject/{数字}
```

**路由值：** `douban_movie:{subject_id}`

**处理逻辑：**
1. 从 URL 中提取 subject ID
2. 调用 `douban_bot.py add movie {subject_id}`
3. 豆瓣自动化脚本执行以下操作：
   - 访问 `https://movie.douban.com/subject/{id}/`
   - 点击「想看」按钮
   - 在弹出对话框中点击「保存」按钮 ✅（关键：需要二次确认）
   - 验证添加成功

**注意：** 点击「想看」后豆瓣会弹出确认框，必须点击「保存」才算真正加入清单。

---

### 规则 2：豆瓣图书链接

**触发条件：** 消息包含以下 URL 格式
```
book.douban.com/subject/{数字}
```

**路由值：** `douban_book:{subject_id}`

**处理逻辑：**
1. 从 URL 中提取 subject ID
2. 调用 `douban_bot.py add book {subject_id}`
3. 豆瓣自动化脚本执行以下操作：
   - 访问 `https://book.douban.com/subject/{id}/`
   - 点击「想读」按钮
   - 在弹出对话框中点击「保存」按钮 ✅（关键：需要二次确认）
   - 验证添加成功

**注意：** 「想读」与「想看」操作流程完全一致，都需要二次点击保存按钮。

---

### 规则 3：待办事项

**触发条件：** 消息包含以下关键词之一（不区分大小写）
```
待办, todo, 记得, 要做, 要搞, 待做, TODO
```

**路由值：** `ima_todo`

**处理逻辑：**
1. 发送消息到 OpenClaw Gateway `/webhook/inbox`
2. Payload 类型标记为 `wechat_todo`
3. 由 OpenClaw 存入 IMA 待办清单

---

### 规则 4：感想/灵感

**触发条件：** 消息包含以下关键词之一（不区分大小写）
```
感想, 想法, 感悟, 思考, 启发, 觉得, 我认为
```

**路由值：** `ima_note`

**处理逻辑：**
1. 发送消息到 OpenClaw Gateway `/webhook/inbox`
2. Payload 类型标记为 `wechat_note`
3. 由 OpenClaw 存入 IMA 感想收集

---

### 规则 5：文章/公众号链接

**触发条件：** 消息包含 HTTP/HTTPS 链接，且不属于豆瓣

**路由值：** `llm_wiki`

**处理逻辑：**
1. 发送链接到 OpenClaw Gateway `/webhook/inbox`
2. Payload 类型标记为 `wechat_article`
3. 由 OpenClaw 摄入 LLM Wiki 知识库

---

### 规则 6：通用收集

**触发条件：** 以上规则均不匹配

**路由值：** `ima_inbox`

**处理逻辑：**
1. 发送消息到 OpenClaw Gateway `/webhook/inbox`
2. Payload 类型标记为 `wechat_inbox`
3. 由 OpenClaw 存入 IMA 通用收集箱

---

## 三、修改指南

### 如何添加新的关键词路由

编辑 `wechat_bot.py` 中的 `parse_and_route()` 函数：

```python
# 在对应位置添加关键词列表
my_keywords = ["新关键词1", "新关键词2"]
if any(kw in content for kw in my_keywords):
    return "my_action"
```

### 如何添加新的 URL 模式

```python
# 在 douban_patterns 后添加新正则
my_pattern = r"example\.com/item/(\d+)"
match = re.search(my_pattern, content)
if match:
    item_id = match.group(1)
    return f"my_action:{item_id}"
```

### 如何修改豆瓣操作的媒体类型

修改 `wechat_bot.py` 中的 `handle_douban_add()` 函数，参数 `media_type` 支持：
- `movie` → 电影/剧集
- `book` → 图书
- `music` → 音乐

---

## 四、OpenClaw Gateway 接口

**Webhook 地址：** `http://localhost:18789/webhook/inbox`

**请求格式：**
```json
{
  "content": "消息原文",
  "source": "wechat",
  "user": "微信用户ID",
  "timestamp": 1700000000
}
```

**来源标记（source 字段）：**
- `wechat` — 普通文本
- `wechat_todo` — 待办事项
- `wechat_note` — 感想
- `wechat_article` — 文章链接
- `wechat_share` — 分享内容
- `wechat_inbox` — 通用收集

---

## 五、日志

运行时日志位置：`~/AI-Fan/tools/douban-bot/wechat_bot.log`

日志格式：
```
[2026-05-04 12:00:00] 📩 收到消息 [文件传输助手]: xxx
[2026-05-04 12:00:01] 🔀 路由结果: douban_movie:12345
[2026-05-04 12:00:02] 📤 回复: ✅ 已添加到豆瓣想看
```

---

**最后更新：** 2026-05-04
**版本：** 1.0
