# 港股期权与 Gamma Scalping 原型

期权希腊值、Delta 再平衡、模拟执行、回测及监控界面的研究原型。

## 模块

- `gamma_scalping/`：富途接口、Black–Scholes 后备计算、合约选择、Delta 再平衡和模拟交易风控。
- `arbitrage_platform/`：早期期权研究平台，包含模拟期权链和简化损益计算。
- `monitor_platform/`：FastAPI 与前端监控原型。
- `simulator/`：模拟账户与行情展示。

Gamma 示例：

```bash
python -m pip install -r requirements.txt
cd gamma_scalping
python web_app.py
```

Python 3.10+。需要本机 FutuOpenD 和相应行情权限；仓库不包含密码或账户标识。Gamma 执行器强制使用模拟环境。其他模块的依赖与启动入口见各子目录，前端使用 `npm install` 和 `npm run dev`。

## 完成度

这是多个历史原型的整理版。模拟期权链和简化损益不等于真实期权回测；行情刷新、订单状态和合约细节尚未端到端复核。接口原型只应在本机或受控开发环境使用，未做生产环境部署加固。此次整理没有连接券商或发送订单。

## 项目说明

维护者：[lhowd301-lab](https://github.com/lhowd301-lab)。本仓库整理自既有课程、研究或工具项目，开发与文档整理使用了 AI 辅助。代码可运行性与研究结论有效性分别说明，不将历史模拟结果视为实盘业绩。
