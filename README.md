# A股连续涨停股票分析系统（中国股市ai自动分析龙头股票）

这是一个用于分析A股市场连续涨停股票的Web应用，它能够自动获取股票数据，识别连续涨停的股票，进行可视化展示，并使用DeepSeek AI进行板块分析和龙头股识别。
<img width="1450" height="741" alt="image" src="https://github.com/user-attachments/assets/f3e6abab-3992-4a41-9d05-9d7d20f4479a" />

<img width="1804" height="694" alt="image" src="https://github.com/user-attachments/assets/eaa71a07-5593-45f5-94e4-d5abc9811b55" />
<img width="1351" height="725" alt="image" src="https://github.com/user-attachments/assets/72fc29be-8492-415a-b6b3-d1bde21f764b" />
<img width="1503" height="788" alt="image" src="https://github.com/user-attachments/assets/4d6bdb6c-9c49-4f62-b520-d978e5ec6207" />

## 功能特点

- 自动获取A股市场连续涨停数据
- 交互式数据可视化展示
  - 行业分布饼图
  - 连续涨停天数条形图
  - 股票数据表格
- 按行业板块分类统计
- 使用DeepSeek AI进行智能分析
- 支持选择不同交易日期
- 增加反包战法（股市大盘下跌时使用，大概率有效）
## 安装要求

1. 确保已安装Python 3.7或更高版本
2. 安装所需依赖包：

```bash
pip install -r requirements.txt
```

## 使用方法
<img width="986" height="425" alt="image" src="https://github.com/user-attachments/assets/c34e71ce-b1dc-4efa-9c8d-ed80a96ad707" />

1. 首先配置DeepSeek API密钥：
   - 打开`main.py`文件
   - 将`your-api-key-here`替换为您的实际API密钥
   - 或者在应用运行后通过侧边栏设置API密钥

2. 运行Streamlit应用：

```bash
streamlit run main.py
```

3. 在浏览器中访问应用（通常是 http://localhost:8501）

## 应用界面说明

应用分为两个主要标签页：

1. **数据可视化**：显示连续涨停股票的可视化图表和数据表格
   - 行业分布饼图：展示不同行业的连续涨停股票分布
   - 连续涨停天数条形图：展示连续涨停天数最多的20只股票
   - 股票数据表格：展示所有连续涨停股票的详细信息

2. **AI分析**：使用DeepSeek AI对连续涨停股票进行深度分析
   - 各行业龙头股特征分析
   - 行业热点分析
   - 投资建议

## 侧边栏功能

- **日期选择**：选择要分析的交易日期
- **API设置**：配置OpenAI API密钥（可选）

## 数据来源

- 股票数据来源于问财API（PyWencai）
- 交易日历数据来源于pandas-market-calendars

## 注意事项

- API调用可能需要付费，请注意控制使用频率
- 本程序仅供参考，投资决策请谨慎
- 远程服务器安装不可用
