# TodoTool 📝

HurricaneSoft 待辦事項管理工具。

## 安裝

```bash
pip install -e .
```

## 設定帳號

方法一：環境變數

```bash
export TODO_USER=admin
export TODO_PASSWORD=your_password
```

方法二：命令列參數

```bash
todotool list --user admin --password your_password
```

## 初始化

```bash
todotool init --admin-user admin --admin-password your_password
```

## 指令範例

```bash
# 新增待辦事項
todotool add "寄報價單給客戶" --priority high --due 2026-02-12 --tag 客戶

# 列出所有待辦
todotool list

# 列出未完成的
todotool list --status pending

# 查詢 7 天內到期
todotool due --days 7

# 標記完成
todotool done 1

# 編輯
todotool edit 1 --title "新標題" --priority low

# 刪除
todotool delete 1

# 查看所有標籤
todotool tag list
```

## 日期格式

到期日請使用 `YYYY-MM-DD` 格式（例：`2026-02-15`）。

## 版本

- v0.1.1 — Bug 修正（--user/--password 參數、日期比較、repo 清理）
- v0.1.0 — 初版
