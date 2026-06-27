# 姿态监控系统 (Camera Man)

USB 摄像头实时坐姿监控，检测驼背/前倾/歪头/久坐/手机使用，Windows 桌面弹窗提醒。

## 功能

| 功能 | 说明 | 阈值 |
|------|------|------|
| 驼背检测 | 耳-肩-髋连线偏离垂直角度 | > 25° |
| 前倾检测 | 上半身与垂直方向夹角 | > 25° |
| 歪头检测 | 双耳连线与水平线夹角 | > 10° |
| 久坐提醒 | 画面中持续检测到人体累计 | 60 分钟 |
| 手机使用 | 手腕靠近脸部 + 头部下倾 | 20 分钟 |
| MinimaX M3 验证 | 多模态模型二次验证（可选） | 托盘手动开关 |

### 去抖与冷却

- 连续 3 帧（15 秒）确认不良姿态后才触发
- 同类型告警冷却 5 分钟
- 画面无人自动暂停所有告警

## 技术栈

Python 3.12 + OpenCV + MediaPipe Pose + pystray + SQLite

## 快速开始

```bash
pip install opencv-python mediapipe pystray Pillow
python main.py
```

## 托盘操作

```
右键托盘图标 →
  ├─ 开始监控     启动摄像头和姿态检测
  ├─ 暂停         停止监控
  ├─ MinimaX 视觉验证  勾选启用 M3 二次验证（需环境变量 minimax_api）
  └─ 退出         关闭程序
```

## MinimaX M3 视觉验证

设置环境变量 `minimax_api` 为 API Key 后，托盘菜单项变为可用。勾选后每帧检测结果会送 Minimax M3 多模态模型做二次验证，API 调用间隔 ≥ 30 秒。

## 模块

```
main.py          主循环 + 去抖状态机 + 久坐/手机计时
camera.py        OpenCV DSHOW 摄像头管理
analyzer.py      MediaPipe Pose 33 关键点 + 角度判定规则
alerter.py       Windows MessageBox 弹窗 + 提示音 + 冷却
storage.py       SQLite 事件记录 + 每日统计
config.py        AppConfig dataclass 默认配置
vision_client.py Minimax M3 API 客户端
tray_ui.py       系统托盘菜单
```

## 判定逻辑

```
摄像头 5s/帧 → MediaPipe 提取 33 关键点 → 规则计算角度
  ├─ 驼背: 耳中点-肩中点-髋中点 三点偏离 180° 超过阈值
  ├─ 前倾: 鼻子-肩中点 与垂直线夹角
  ├─ 歪头: 左耳-右耳 与水平线夹角
  └─ 手机: 手腕距鼻子 < 0.18 + 头低于肩

逐帧 → 去抖(3帧confirm) → 冷却检查 → 弹窗 + 写库
久坐/手机 → 每 60s tick → 累计超阈值 → 弹窗
```

## 数据

SQLite 存储在 `data/posture.db`，两张表：
- `events` — 事件明细
- `daily_stats` — 每日汇总

## 开发历史

本项目通过 superpowers SDD 流程开发：spec → plan → TDD → subagent-driven-development，7 个任务模块，40 个单元测试，16 次 commit。
