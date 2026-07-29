# GB/T 40432—2021 合规层使用说明

## 1. 设计原则

国标参数作为整机合规目标和试验边界，不直接覆盖硬件采样链设计参数。工具采用三层模型：

1. GB/T 40432—2021 整机限值；
2. 产品级设计目标；
3. IAC、IDC、VAC、VDC采样链误差、量程、带宽和延迟预算。

例如，国标直流输出电压误差为±1%，默认只将其中50%分配给VDC采样链，因此采样目标仍为0.5%FS，而不是放宽到1%。

## 2. 配置入口

标准配置文件：

```text
config/standards/gbt40432_2021.yaml
```

设计配置中的`standard_profile.enabled`为`true`时，工具自动生成合规层。也可以通过CLI在运行时合并：

```bash
python run_mvp.py calculate \
  --config config/pmp23607_user.yaml \
  --standard config/standards/gbt40432_2021.yaml \
  --output results/PMP23607_GBT40432_ADC_Sensing_Design_v0p3.xlsx \
  --json results/PMP23607_GBT40432_ADC_Sensing_Design_v0p3.json
```

## 3. 新增Excel工作表

- `02_GBT_Compliance`：标准适用范围、输入测试电压、启动冲击量程、VDC/IDC误差分配、PF与效率筛查。
- `03_GBT_Test_Matrix`：电压、频率、三相相位偏差、启动、误差、纹波、效率、电压暂降和保护测试点。
- `04_GBT_Allocation`：明确哪些原设计参数保留、哪些增加独立合规参数、哪些不能直接替换。
- `07_GBT_Test_Equipment`：测试仪表精度等级、位数和环境试验设备要求。
- `08_GBT_Safety_EMC`：温湿度、绝缘电阻、耐压、接触电流、浪涌、EFT、ESD和辐射抗扰要求。
- `09_GBT_Inverter`：双向OBC逆变模式的输出电压、频率、动态响应、THD、直流分量与效率要求。

## 4. 结果解释

- `PASS`：当前配置覆盖该合规设计边界。
- `WARNING`：设计参数与国标测试名义值不同，或配置值不能作为型式试验证据。
- `FAIL`：硬件范围、误差分配或裕量不能满足当前合规层检查。
- `NOT_EVALUATED`：缺少器件耐压、EMC、延迟或误差等证据，工具不会用0代替。

## 5. 限制

合规层是设计预检查，不替代正式型式试验。以下项目仍需实测：整机输出误差、纹波、功率因数、平均效率、EMC、耐压、接触电流、逆变THD、动态恢复和并网电流直流分量。
