# tests

自动测试目录。当前测试覆盖:

- SAC 二进制头段中的 `stla/stlo` 读取。
- SAC 空值 `-12345` 和 `0,0` 经纬度过滤。
- 从 `S行号_Z_列号.sac` 文件名解析二维阵列坐标。
- 阵列坐标到经纬度的近似投影。

运行:

```bash
uv run --no-sync python -m pytest -q
```
