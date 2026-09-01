# frontend · WIKI 本地知识库

Vue 3 + TypeScript + Element Plus + Vite + Pinia + Vue Router。

## 开发

```bash
cd frontend
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5173`  
代理目标：`VITE_PROXY_TARGET`（默认 `http://127.0.0.1:5000`）

## 生产构建（由后端托管）

```bash
npm run build
# 产物：frontend/dist
# 启动后端后访问 http://127.0.0.1:5000/
```

商业构建：`npm run build:commercial`。

## 说明

- 工程形态对标 `wiki-admin-ui`（request / router / store / layout），**未复制**票务等业务页
- 视觉令牌见 `src/assets/styles/tokens.css`（对齐 `deliverables/prototype/design-spec.md`）
- 版本：`VITE_EDITION=community|commercial`；**禁止**界面内切换版本
- 商业专属页：`src/views/commercial/`（社区 `build_edition` 会剔除）；锁态示意用 `EditionGate`
- 社区开发 / 构建：`npm run dev` / `npm run build`
- 商业开发 / 构建：`npm run dev:commercial` / `npm run build:commercial`
- 发版隔离细则：`docs/商业版功能开发计划-专属与增强.md` §7
- 原静态台已归档至 `archive/web/`；新功能只在本目录开发
