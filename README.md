# Digital Delivery Telegram Bot

一个面向通用数字服务的 Telegram 预约与次日人工交付系统。

## 已实现

- X → Telegram `start` 参数来源归因
- Telegram Bot 商品浏览、条款确认和订单查询
- 商品分类、库存显示与 1/2/5 件数量选择
- 下单时原子预留库存；取消/过期订单释放库存
- 0 定金直接预约
- USDT 定金/尾款的人工核验与链上交易哈希去重
- 管理后台确认到账并向客户发送状态通知
- 管理后台人工交付，正文直接发送且不写入订单日志
- 次日交付时间计算
- FastAPI 管理接口
- Vue 3.5 管理后台
- 商品、活动链接和订单状态管理
- MySQL 订单、支付、状态历史与幂等数据结构

## 本机启动

1. 复制 `.env.example` 为 `.env` 并填写数据库、Bot Token、管理密钥、USDT 网络及公共收款地址。
2. 创建数据库：`digital_delivery_bot`，字符集 `utf8mb4`。
3. 安装后端依赖并启动：

   ```bash
   python3.12 -m venv .venv
   .venv/bin/pip install -r backend/requirements-dev.txt
   .venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
   ```

4. 安装前端依赖并构建后台：

   ```bash
   cd frontend
   npm install
   npm run build
   ```

5. 打开 `http://127.0.0.1:8001/admin/`，使用 `.env` 中的 `ADMIN_API_KEY` 登录。

## Bot 命令

- `/start`：进入商品选择
- `/products`：查看商品
- `/orders`：查看最近订单
- `/txid <订单号> <交易哈希>`：提交 USDT 交易哈希
- `/terms`：服务条款
- `/support`：人工客服
- `/paysupport`：支付支持

## X 链接

在帖子中使用：

```text
https://t.me/ClaudeSpecialbot?start=x_default
```

后台可创建不同 campaign code，以区分帖子、广告或合作渠道。

## 安全说明

- `.env` 已被 Git 忽略，不要提交 Token、密码或管理密钥。
- USDT 到账目前由运营人员检查交易哈希后手动确认；尚未集成链上自动监控、二维码支付或 10 分钟付款过期机制。
- 商品库存留空表示不限库存；将商品数量设为 0 会在用户端显示售罄。商品价格和定金按件计算。
- USDT 订单由后台人工核验交易哈希，不会仅凭客户提交的哈希自动标记到账。
- 管理接口通过 `X-Admin-Key` 保护。当前监听 `127.0.0.1`，对外开放前应配置 HTTPS 反向代理。
- 生产环境建议将密钥迁移到系统 Secret 管理服务。
- 管理后台的交付弹窗会把内容直接发给对应 Telegram 客户；正文不会存入订单记录或审计日志。
- 不要把私钥、助记词或交易所登录信息放进 `.env` 或订单交付内容。

