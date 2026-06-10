# AHarbitrage Web

AH 股比价数据管理平台，提供文件上传、比价数据搜索下载、图表生成功能。

---

## 项目结构

```
├── docker-compose.yml           # 容器编排
├── Dockerfile                   # nginx 镜像
├── nginx.conf                   # 反向代理路由
├── html/                        # 前端（纯静态）
│   ├── index.html
│   ├── style.css
│   └── app.js
├── backend/                     # Flask 后端
│   ├── app.py                   # 应用入口
│   ├── config.py                # 路径常量
│   ├── state.py                 # 全局内存状态
│   ├── auth.py                  # 认证、会话、锁定
│   ├── upload_api.py            # 文件上传
│   ├── download_api.py          # 搜索、下载、打包
│   ├── chart_api.py             # 图表生成
│   ├── chart_common.py          # 绘图公共模块
│   ├── logger.py                # 日志
│   ├── gen_password.py          # 密码生成工具
│   ├── users.txt                # 用户密码文件
│   ├── requirements.txt
│   └── Dockerfile
└── .vscode/settings.json
```

---

## 功能

### 1. 用户认证

- 登录 / 登出 / 会话检查
- SHA-256 盐值哈希存储密码，不可逆向
- 5 次失败锁定 30 分钟，指数退避延迟
- 单用户单 session：同账号新登录踢旧登录
- 紧急解锁（用户名 `_unlock`）
- 前端被踢出后 60 秒自动返回登录页

### 2. 文件上传

| 功能 | 接口 | 目标文件 |
|------|------|---------|
| 更新股票监控表 | `POST /update_ah_rate` | `{ROOT_DIR}/config/ah_stock_map.csv` |
| 更新溢价监控表 | `POST /premium_update` | `{ROOT_DIR}/config/ah_alarmRate.csv` |

- 拖拽或点击选择 CSV 文件上传
- 自动检测编码（UTF-8 / GBK / GB2312）并转为 UTF-8 存储

### 3. 比价文件搜索下载

| 输入格式 | 行为 |
|---------|------|
| `yyyyMMdd` | 单日搜索，列出匹配文件逐个下载 |
| `yyyyMMdd-yyyyMMdd` | 日期范围，打包为 zip 下载 |

- 输入 A 股 6 位代码
- 遍历路径：`{ROOT_DIR}/{yyyy}_ah比价/{yyyyMMdd}_ah比价/{代码}*.csv`

### 4. 图表生成

| 功能 | 接口 | 图表类型 |
|------|------|---------|
| AH 股走势图 | `GET /chart_lines` | 多列折线图 |
| 溢价率柱状图 | `GET /chart_bars` | a/h_rate 柱状图 |

**走势图参数：**
- 日期范围 `yyyyMMdd-yyyyMMdd`
- A 股代码（6 位）
- 频率：`daily` / `weekly` / `hourly`
- 列（可多选）：a_price、h_price、a/h_rate、a_high、a_low、h_high、h_low

**柱状图参数：**
- 日期范围 `yyyyMMdd-yyyyMMdd`
- A 股代码（6 位）
- 频率：`daily` / `weekly` / `hourly`

### 5. 安全防护

- 密码不可逆哈希存储
- 登录 IP 频率限制（每分钟 20 次）
- 账户锁定跨 worker 共享（文件存储）
- 路径遍历防护
- Session 过期自动清理

---

## 部署

### 前置条件

- Docker & Docker Compose
- ECS 宿主机目录 `/home/harry/data/` 下需存在：
  - `config/users.txt`（用户密码文件）
  - `{yyyy}_ah比价/{yyyyMMdd}_ah比价/{代码}*.csv`（比价数据文件）

### 部署步骤

```bash
cd AHarbitrage_server

# 编辑密码文件
vim backend/users.txt

# 检查 docker-compose.yml 中的 ROOT_DIR 和 volumes

# 构建并启动
docker compose up -d --build

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

### docker-compose.yml 示例

```yaml
services:
  nginx:
    build: .
    ports:
      - "8080:80"
    depends_on:
      - flask-backend

  flask-backend:
    build: ./backend
    volumes:
      - /home/harry/data:/app/data
    environment:
      - ROOT_DIR=/app/data
      - SECRET_KEY=your-random-secret-key
    expose:
      - "8000"
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ROOT_DIR` | `/home/harry` | 文件系统根路径，所有业务文件基于此 |
| `SECRET_KEY` | 随机生成 | Flask session 加密密钥，**生产环境必须设为固定值** |
| `LOG_LEVEL` | `INFO` | 日志级别：DEBUG / INFO / WARNING / ERROR / CRITICAL |

---

## 密码管理

```bash
# 交互式输入（密码不可见）
python3 backend/gen_password.py

# 命令行传参
python3 backend/gen_password.py admin mypassword
```

输出行追加到 `{ROOT_DIR}/config/users.txt`。文件格式：

```
# 注释行
用户名:盐值:SHA256哈希
!unlock:盐值:哈希     # 紧急解锁密钥，用户名 _unlock
```

---

## 本地开发

```bash
# 后端
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
ROOT_DIR=/home/harry/data python3 app.py    # 监听 :8000

# 前端
cd html
python3 -m http.server 8080                 # 监听 :8080
```

访问 `http://localhost:8080` 查看页面。本地没有 nginx 代理，API 请求需直接访问 Flask 端口。

---

## 日志

- 格式：`时间 | 级别 | 模块 | [用户] 消息`
- 路径：`{ROOT_DIR}/log/web/{日期}/AHarbitrage_web_{日期}_{编号}.log`
- 单文件 10MB 自动轮转，新文件编号递增
- 同时输出到控制台
