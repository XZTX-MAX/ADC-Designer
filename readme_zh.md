# F29H85x OBC ADC 感知设计器 MVP v0.3

这是一个用于单相和三相双向单级 OBC 平台的一阶段电流/电压感知设计的确定性 Python 计算器。

## 核心设计范围

### 保留的单相支持

- PMP23607/F29H85x 回归配置文件
- 双向 IAC/IDC 范围计算
- 霍尔传感器、分流/隔离放大器、VAC 和 VDC 计算
- 模拟滤波、ADC 采样、延迟以及 WC/RSS 误差计算

### 新增的三相支持

- 三相线电流方程：
  - 线对线输入：`P/(sqrt(3)*VLL*eta*PF)`
  - 相对中性点输入：`P/(3*Vphase*eta*PF)`
- 可配置的相位不平衡设计系数
- 每相电流和电压通道实例，支持独立覆盖配置
- 双电流传感器模式，并提供显式的 KCL 重建警告
- 相位通道增益、零点和分压比匹配计算
- 同步采样模型：
  - 共用 ePWM 触发一致性
  - 直接测量相电流时的 ADC 模块分配检查
  - 采样孔径偏移
  - 线频率和开关频率角度偏移
  - `di/dt * skew` 和 `dv/dt * skew` 误差估计
- 三相 Excel 和 JSON 报告输出

## 快速开始

单相 PMP23607 回归示例：

```bash
python run_mvp.py validate --config config/pmp23607_default.yaml
python run_mvp.py calculate \
  --config config/pmp23607_default.yaml \
  --output results/PMP23607_ADC_Sensing_Design_v0p2.xlsx \
  --json results/PMP23607_ADC_Sensing_Design_v0p2.json
```

三相模板示例：

```bash
python run_mvp.py validate --config config/three_phase_22kw_template.yaml
python run_mvp.py calculate \
  --config config/three_phase_22kw_template.yaml \
  --output results/Three_Phase_22kW_ADC_Sensing_Design.xlsx \
  --json results/Three_Phase_22kW_ADC_Sensing_Design.json
```

三相 22 kW 的 YAML 文件是一个“暂定架构模板”，并不是已发布的 PMP41186 规范。请在正式发布设计前替换电压范围、传感器参数、ADC 分配、延迟边界和误差源。

## 三相配置块

```yaml
system:
  phase_count: 3
  ac_voltage_basis: line_to_line
  phase_unbalance_factor: 1.05

channels:
  iac:
    phase_names: [A, B, C]
    phase_overrides: {}
  vac:
    measurement_basis: phase_to_neutral
    phase_names: [A, B, C]
    phase_overrides: {}

sampling:
  trigger_source: EPWM1_SOCA
  trigger_position: PWM_CENTER
  simultaneous_required: true
  maximum_channel_skew_s: 1.0e-7
  channels:
    - name: IAC_A
      quantity: current
      adc_module: ADCA
      soc: 0
      aperture_delay_s: 0.0
```

## Fail-closed（失效关闭）行为

- 缺少精确的 F29H85x 内部 ADC 参数时，结果保持为 `NOT_EVALUATED`
- 缺少延迟或误差输入时，不会自动替换为 0
- 共享同一 ADC 模块的直接相电流会导致同步采样要求失败
- 缺少每相采样分配时，会导致校验和报告检查失败
- 仅在显式配置时，才允许使用双电流传感器重建模式

## 测试

```bash
python -m unittest discover -s tests -v
```

回归测试同时覆盖了原有的 PMP23607 计算、全新的三相公式、每相通道生成、线电压/相电压换算、匹配计算以及采样偏移模型。

## GB/T 40432—2021 合规层（v0.3）

设计配置文件现在包含 `standard_profile` 块。它不会替代硬件和控制设计参数，而是增加了一层独立的整机合规性/测试分析层，用于检查从产品极限到感知链目标的分配关系。

生成的合规章节包括：

- `02_GBT_Compliance`：适用性、交流测试范围、启动涌流、感知误差分配、启动范围裕度、功率因数和效率筛选
- `03_GBT_Test_Matrix`：电压/频率/相位、启动、误差、纹波、效率和电压跌落测试点
- `04_GBT_Allocation`：明确说明哪些默认值保留、补充或替换
- `07_GBT_Test_Equipment`：参考仪器精度和环境测试设备要求
- `08_GBT_Safety_EMC`：温度、绝缘、介电、接触电流、浪涌、EFT、ESD 和辐射抗扰要求
- `09_GBT_Inverter`：双向/反向功率运行的附录 A 要求

可复用的标准层位于：

```text
config/standards/gbt40432_2021.yaml
```

可以在运行时合并使用：

```bash
python run_mvp.py calculate \
  --config config/pmp23607_default.yaml \
  --standard config/standards/gbt40432_2021.yaml \
  --output results/PMP23607_GBT40432_ADC_Sensing_Design.xlsx \
  --json results/PMP23607_GBT40432_ADC_Sensing_Design.json
```

关键设计规则：标准中的 ±1% 电压极限和分段电流极限属于整机极限，并不会自动复制到 `channels.*.accuracy_target_percent_fs`。计算器会使用可配置的感知误差分配比例来进行计算。
