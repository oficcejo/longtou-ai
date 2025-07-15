import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pywencai
import pandas_market_calendars as mcal
from datetime import datetime, timedelta
from openai import OpenAI
import time
import os
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch, cm
import base64
# 添加中文字体支持
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 注册Windows默认中文字体（如果是其他系统，路径需要相应调整）
try:
    # Windows 系统默认中文字体
    CHINESE_FONT_PATH = "C:/Windows/Fonts/simhei.ttf"
    pdfmetrics.registerFont(TTFont('SimHei', CHINESE_FONT_PATH))
except:
    try:
        # Linux/Mac系统可能的中文字体路径
        CHINESE_FONT_PATH = "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"
        pdfmetrics.registerFont(TTFont('DroidSansFallback', CHINESE_FONT_PATH))
    except:
        st.warning("未能找到合适的中文字体，PDF中的中文可能无法正确显示")

# 设置页面配置
st.set_page_config(page_title="A股连续涨停分析工具", page_icon="📈", layout="wide")

# 初始化OpenAI客户端（用于DeepSeek API）
client = OpenAI(
    base_url="https://api.deepseek.com",  # DeepSeek API 地址
    api_key='sk-b6c714570b9844f392aa3812f3f7a7fc'  # 替换为您的API密钥
)

# 获取交易日历
def get_trading_days(start_date, end_date):
    """获取指定日期范围内的交易日"""
    # 使用上海证券交易所日历
    sse = mcal.get_calendar('XSHG')  # 使用XSHG代码，与用户代码保持一致
    trading_days = sse.schedule(start_date=start_date, end_date=end_date)
    return trading_days.index.strftime('%Y-%m-%d').tolist()  # 保持YYYY-MM-DD格式，在使用时再转换

# 获取连续涨停股票数据
def get_continuous_limit_up_stocks(date=None):
    """获取指定日期的连续涨停股票数据"""
    if date is None:
        date = datetime.now().strftime('%Y%m%d')  # 使用YYYYMMDD格式
    else:
        # 确保日期格式为YYYYMMDD
        if '-' in date:
            date = date.replace('-', '')
    
    try:
        # 使用问财获取连续涨停数据
        query = f"非ST，{date}连续涨停天数排序,概念"
        data = pywencai.get(query=query)
        
        if data is None or len(data) == 0:
            st.info(f"{date} 没有获取到数据")
            return None
        
        # 打印列名，帮助调试
        st.write("获取到的数据列名:", list(data.columns))
        
        # 找到对应日期的连续涨停天数列名
        limit_up_col = None
        for col in data.columns:
            if '连续涨停天数' in col or '连板' in col:
                limit_up_col = col
                break
        
        if limit_up_col is None:
            # 尝试使用特定格式的列名
            limit_up_col = f'连续涨停天数[{date}]'
            if limit_up_col not in data.columns:
                st.error(f"未找到连续涨停天数列，可用列名: {list(data.columns)}")
                return None
        
        # 创建新的DataFrame以存储处理后的数据
        processed_data = pd.DataFrame()
        
        # 处理股票代码
        if '股票代码' in data.columns:
            processed_data['code'] = data['股票代码']
        elif '代码' in data.columns:
            processed_data['code'] = data['代码']
        else:
            st.error("未找到股票代码列")
            return None
        
        # 处理股票名称
        if '股票简称' in data.columns:
            processed_data['name'] = data['股票简称']
        elif '名称' in data.columns:
            processed_data['name'] = data['名称']
        else:
            st.error("未找到股票名称列")
            return None
        
        # 处理行业
        if '所属概念' in data.columns:
            processed_data['industry'] = data['所属概念']
        elif '概念' in data.columns:
            processed_data['industry'] = data['概念']
        elif '概念名称' in data.columns:
            processed_data['industry'] = data['概念名称']
        else:
            # 如果找不到行业列，创建一个默认值
            processed_data['industry'] = '未知概念'
            st.warning("未找到概念数据列，使用'未知概念'作为默认值")
        
        # 处理涨停天数
        processed_data['limit_up_days'] = pd.to_numeric(data[limit_up_col], errors='coerce')
        
        # 过滤掉非连续涨停的股票
        processed_data = processed_data[processed_data['limit_up_days'] >= 1]  # 包含首板
        
        # 如果数据为空，返回None
        if len(processed_data) == 0:
            st.info(f"{date} 没有连续涨停的股票")
            return None
            
        return processed_data
    
    except Exception as e:
        st.error(f"获取数据时出错: {e}")
        import traceback
        st.error(traceback.format_exc())  # 打印详细错误信息
        return None

# 分析行业龙头
def analyze_industry_leaders(stocks_df):
    """分析行业龙头股票和跟随股票"""
    if stocks_df is None or len(stocks_df) == 0:
        return "未找到连续涨停的股票。"
    
    # 按行业分组
    industry_groups = stocks_df.groupby('industry')
    
    analysis_prompt = """
    以下是连续涨停股票数据，请详细分析每个行业的龙头股票和跟随股票：
    
    {}
    
【输入数据参数】  
- 连续涨停股票列表：包含代码、名称、涨停天数 

【分析逻辑模块】  
找出热门板块，按所属板块分组，分析每个板块的龙头股和跟随股票。以表格形式输出
一只股票可以同时属于多个板块，需要分析每个板块的龙头股和跟随股票。
热门板块的判断标准：
1. 板块的涨停股票数量大于3只
2、按板块内涨停板股票数量进行排名，并列出所属股票清单
3、涨停板占总数30%以上的板块升级为主线板块

【输出结果要求】
总结每个板块的龙头股和跟随股票，并给出操作建议。



    """
    
    # 格式化股票数据，按连续涨停天数排序
    formatted_data = ""
    for industry, group in industry_groups:
        # 按连续涨停天数降序排序
        sorted_group = group.sort_values('limit_up_days', ascending=False)
        formatted_data += f"\n## {industry}行业:\n"
        formatted_data += f"该行业共有{len(sorted_group)}只连续涨停股票\n"
        
        # 添加表格头部
        formatted_data += "| 股票名称 | 股票代码 | 连续涨停天数 |\n"
        formatted_data += "| ------ | ------ | ------ |\n"
        
        # 添加股票数据
        for _, row in sorted_group.iterrows():
            formatted_data += f"| {row['name']} | {row['code']} | {row['limit_up_days']} |\n"
    
    try:
        # 调用DeepSeek API进行分析
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的股票分析师，擅长分析A股市场的连续涨停股票和行业板块，判定行业龙头和跟随股，并对行业轮动机制进行分析。"},
                {"role": "user", "content": analysis_prompt.format(formatted_data)}
            ],
            temperature=0.7,  # 控制创造性，较低的值使输出更确定性
            max_tokens=4000   # 控制回复长度
        )
        
        # 新版API的返回结果结构不同
        return response.choices[0].message.content
    
    except Exception as e:
        st.error(f"AI分析时出错: {e}")
        import traceback
        st.error(traceback.format_exc())  # 打印详细错误信息
        return "AI分析失败，请稍后再试。"

# 可视化连续涨停数据
def visualize_limit_up_data(stocks_df, date):
    """可视化连续涨停数据"""
    if stocks_df is None or len(stocks_df) == 0:
        st.info(f"{date} 没有连续涨停的股票。")
        return
    
    # 1. 行业分布饼图
    industry_counts = stocks_df.groupby('industry').size().reset_index(name='count')
    industry_counts = industry_counts.sort_values('count', ascending=False)
    
    fig_pie = px.pie(
        industry_counts, 
        values='count', 
        names='industry',
        title=f"{date} 连续涨停股票行业分布",
        hole=0.4,
    )
    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
    st.plotly_chart(fig_pie, use_container_width=True)
    
    # 2. 连续涨停天数条形图
    fig_bar = px.bar(
        stocks_df.sort_values('limit_up_days', ascending=False).head(20), 
        x='name', 
        y='limit_up_days',
        color='industry',
        title=f"{date} 连续涨停天数最多的20只股票",
        labels={'name': '股票名称', 'limit_up_days': '连续涨停天数', 'industry': '所属概念'}
    )
    st.plotly_chart(fig_bar, use_container_width=True)
    
    return fig_pie, fig_bar

# 生成PDF报告
def generate_pdf_report(stocks_df, date, analysis_text):
    """生成PDF分析报告 - 使用表格代替图表"""
    # 创建临时文件
    temp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(temp_dir, f"连续涨停分析报告_{date}.pdf")
    
    # 创建PDF文档
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    
    # 获取系统支持的中文字体名称
    chinese_font_name = 'SimHei' if os.path.exists("C:/Windows/Fonts/simhei.ttf") else 'DroidSansFallback'
    
    # 自定义标题样式
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Title'],
        fontSize=18,
        alignment=1,  # 居中
        spaceAfter=20,
        fontName=chinese_font_name  # 使用中文字体
    )
    
    # 自定义小标题样式
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=10,
        fontName=chinese_font_name  # 使用中文字体
    )
    
    # 自定义正文样式
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        fontName=chinese_font_name  # 使用中文字体
    )
    
    # 修改默认样式中的字体
    for style in styles.byName.values():
        style.fontName = chinese_font_name
    
    # 创建文档内容
    content = []
    
    # 添加标题
    content.append(Paragraph(f"A股连续涨停分析报告 - {date}", title_style))
    content.append(Spacer(1, 0.5*cm))
    
    # 添加生成时间
    content.append(Paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    content.append(Spacer(1, 0.5*cm))
    
    # 添加股票数据表格
    if stocks_df is not None and len(stocks_df) > 0:
        content.append(Paragraph("连续涨停股票数据", subtitle_style))
        content.append(Spacer(1, 0.3*cm))
        
        # 准备表格数据
        table_data = [["股票代码", "股票名称", "所属概念", "连续涨停天数"]]
        
        # 按连续涨停天数排序
        sorted_df = stocks_df.sort_values('limit_up_days', ascending=False)
        
        # 添加股票数据行
        for _, row in sorted_df.iterrows():
            # 用Paragraph包裹industry字段，实现自动换行
            industry_para = Paragraph(str(row['industry']), ParagraphStyle(
                'industry_cell', parent=body_style, alignment=0, wordWrap='CJK', fontName=chinese_font_name, fontSize=9, leading=12, spaceAfter=0, spaceBefore=0
            ))
            table_data.append([row['code'], row['name'], industry_para, str(row['limit_up_days'])])
        
        # 创建表格，调整所属概念列宽为5cm
        table = Table(table_data, colWidths=[2*cm, 3*cm, 5*cm, 2.5*cm])
        
        # 设置表格样式
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), chinese_font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ])
        
        # 为交替行添加背景色
        for i in range(1, len(table_data), 2):
            table_style.add('BACKGROUND', (0, i), (-1, i), colors.lightgrey)
        
        table.setStyle(table_style)
        content.append(table)
        content.append(Spacer(1, 0.5*cm))
    
    # 添加涨停天数分布表格
    content.append(Paragraph("连续涨停天数排名", subtitle_style))
    content.append(Spacer(1, 0.3*cm))
    
    # 创建涨停天数分布表格
    if stocks_df is not None and len(stocks_df) > 0:
        days_count = stocks_df['limit_up_days'].value_counts().reset_index()
        days_count.columns = ['days', 'count']
        days_count = days_count.sort_values('days')
        
        days_table_data = [['连续涨停天数', '股票数量', '占比']]
        total_stocks = len(stocks_df)
        
        for _, row in days_count.iterrows():
            percentage = f"{row['count'] / total_stocks * 100:.1f}%"
            days_table_data.append([str(row['days']), str(row['count']), percentage])
        
        days_table = Table(days_table_data, repeatRows=1)
        days_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), chinese_font_name),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        # 为交替行添加背景色
        for i in range(1, len(days_table_data), 2):
            days_table.setStyle(TableStyle([('BACKGROUND', (0, i), (-1, i), colors.lightgrey)]))
        
        content.append(days_table)
        content.append(Spacer(1, 0.5*cm))
    
    # 添加AI分析结果
    if analysis_text:
        content.append(Paragraph("DeepSeek AI 分析结果", subtitle_style))
        content.append(Spacer(1, 0.3*cm))
        
        # 处理Markdown格式的分析文本
        # 简单处理：按行分割，识别标题和段落
        lines = analysis_text.split('\n')
        current_paragraph = ""
        
        for line in lines:
            # 处理标题
            if line.startswith('# '):
                if current_paragraph:
                    content.append(Paragraph(current_paragraph, body_style))
                    content.append(Spacer(1, 0.2*cm))
                    current_paragraph = ""
                content.append(Paragraph(line[2:], styles['Heading1']))
                content.append(Spacer(1, 0.3*cm))
            elif line.startswith('## '):
                if current_paragraph:
                    content.append(Paragraph(current_paragraph, body_style))
                    content.append(Spacer(1, 0.2*cm))
                    current_paragraph = ""
                content.append(Paragraph(line[3:], styles['Heading2']))
                content.append(Spacer(1, 0.2*cm))
            elif line.startswith('### '):
                if current_paragraph:
                    content.append(Paragraph(current_paragraph, body_style))
                    content.append(Spacer(1, 0.2*cm))
                    current_paragraph = ""
                content.append(Paragraph(line[4:], styles['Heading3']))
                content.append(Spacer(1, 0.2*cm))
            # 处理表格（简化处理）
            elif line.startswith('|') and '|' in line[1:]:
                if current_paragraph:
                    content.append(Paragraph(current_paragraph, body_style))
                    content.append(Spacer(1, 0.2*cm))
                    current_paragraph = ""
                content.append(Paragraph(line, body_style))
            # 处理空行
            elif line.strip() == "":
                if current_paragraph:
                    content.append(Paragraph(current_paragraph, body_style))
                    content.append(Spacer(1, 0.2*cm))
                    current_paragraph = ""
            # 处理普通段落
            else:
                if current_paragraph:
                    current_paragraph += " " + line
                else:
                    current_paragraph = line
        
        # 添加最后一个段落
        if current_paragraph:
            content.append(Paragraph(current_paragraph, body_style))
    
    # 构建PDF
    doc.build(content)
    
    return pdf_path

# 创建下载链接
def get_pdf_download_link(pdf_path, filename):
    """创建PDF下载链接，带有美观的按钮样式"""
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    
    b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    
    # 创建一个美观的下载按钮
    download_button_str = f'''
    <a href="data:application/pdf;base64,{b64_pdf}" download="{filename}" 
       style="display: inline-flex; align-items: center; justify-content: center; 
              background-color: #4CAF50; color: white; padding: 12px 20px; 
              text-decoration: none; border-radius: 4px; font-weight: bold; 
              font-size: 16px; margin: 10px 0; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" 
             fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" 
             stroke-linejoin="round" style="margin-right: 8px;">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
        下载PDF分析报告
    </a>
    '''
    
    return download_button_str

# 获取一进二股票数据
def get_one_to_two_candidates(date=None):
    """获取一进二（昨日首板，今日大概率进2板）股票数据"""
    if date is None:
        today = datetime.now().strftime('%Y%m%d')
    else:
        today = date.replace('-', '') if '-' in date else date
    yesterday = (datetime.strptime(today, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
    query = f"沪深主板，非st，前日涨停，昨日未涨停，今日竞价涨幅，今日竞价量，昨日成交量"
    try:
        data = pywencai.get(query=query)
        if data is None or len(data) == 0:
            return None
        # 字段名严格按问财返回
        code_col = '股票代码'
        name_col = '股票简称'
        open_rise_col = f'竞价涨幅[{today}]'
        today_vol_col = f'竞价量[{today}]'
        yest_vol_col = f'成交量[{yesterday}]'
        # 构建DataFrame
        df = pd.DataFrame()
        df['code'] = data[code_col]
        df['name'] = data[name_col]
        df['open_rise'] = pd.to_numeric(data[open_rise_col], errors='coerce') if open_rise_col in data.columns else None
        df['today_vol'] = pd.to_numeric(data[today_vol_col], errors='coerce') if today_vol_col in data.columns else None
        df['yest_vol'] = pd.to_numeric(data[yest_vol_col], errors='coerce') if yest_vol_col in data.columns else None
        # 计算竞昨比
        df['竞昨比'] = df.apply(lambda row: row['today_vol'] / row['yest_vol'] * 100 if row['yest_vol'] and row['yest_vol'] != 0 else None, axis=1)
        # 判断大概率进2板
        def judge(row):
            if pd.isna(row['open_rise']) or pd.isna(row['竞昨比']):
                return ''
            # 竞价涨幅在-10%到-5%之间，且竞昨比>5%
            if -10 <= row['open_rise'] < -5 and row['竞昨比'] > 5:
                return '★大概率反包'
            # 竞价涨幅在0到-4.99%之间，且竞昨比>2.5%
            if -5 <= row['open_rise'] < 0 and row['竞昨比'] > 2.5:
                return '★大概率反包'
            return ''
        df['进2板概率'] = df.apply(judge, axis=1)
        df = df[['code', 'name', 'open_rise', 'today_vol', 'yest_vol', '竞昨比', '进2板概率']]
        st.write("问财返回的列名：", list(data.columns))
        st.write("问财部分原始数据：", data.head())
        return df
    except Exception as e:
        st.error(f"一进二数据获取出错: {e}")
        import traceback
        st.error(traceback.format_exc())
        return None

# 主应用
def main():
    st.title("📈 A股连续涨停分析工具")
    st.markdown("""这个应用帮助您跟踪A股市场中连续涨停的股票，分析行业热点和龙头股。""")
    
    # 侧边栏 - 日期选择
    with st.sidebar:
        st.header("设置")
        
        # 获取最近30天的交易日
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        trading_days = get_trading_days(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        
        if not trading_days:
            st.error("无法获取交易日信息")
            return
        
        # 将日期格式转换为YYYYMMDD格式，用于显示
        trading_days_display = [day.replace('-', '') for day in trading_days]
        
        # 默认选择最新的交易日
        selected_date = st.selectbox(
            "选择交易日期",
            options=trading_days_display,
            index=len(trading_days_display)-1
        )
        
        # API密钥设置（可选）
        st.subheader("API设置（可选）")
        api_key = st.text_input("DeepSeek API密钥", type="password")
        if api_key:
            # 重新初始化客户端，使用新的API密钥
            global client
            client = OpenAI(
                base_url="https://api.deepseek.com",
                api_key=api_key
            )
    
    # 主界面
    tab0, tab1, tab2 = st.tabs(["🚀 反包精选", "📊 数据可视化", "🔍 AI分析"])
    
    # 一进二栏目
    with tab0:
        st.subheader("🚀 反包（前日涨停，昨日未涨停，今日大概率反包）")
        with st.spinner("正在获取反包数据..."):
            one_to_two_df = get_one_to_two_candidates(selected_date)
        if one_to_two_df is not None and len(one_to_two_df) > 0:
            st.success(f"共找到 {len(one_to_two_df)} 只昨日首板股票")
            st.dataframe(
                one_to_two_df.sort_values('进2板概率', ascending=False),
                use_container_width=True,
                column_config={
                    'code': '股票代码',
                    'name': '股票名称',
                    'open_rise': '竞价涨幅(%)',
                    'today_vol': '今日竞价量',
                    'yest_vol': '昨日成交量',
                    '竞昨比': '竞昨比(%)',
                    '进2板概率': '进2板概率标记'
                }
            )
            st.caption('★为大概率进2板股票，竞昨比=今日竞价量/昨日成交量*100')
        else:
            st.info(f"{selected_date} 没有符合条件的一进二股票。")
    
    # 获取数据
    with st.spinner("正在获取连续涨停数据..."):
        stocks_df = get_continuous_limit_up_stocks(selected_date)
    
    # 数据可视化标签页
    with tab1:
        if stocks_df is not None and len(stocks_df) > 0:
            st.success(f"找到 {len(stocks_df)} 只连续涨停股票")
            
            # 可视化数据
            fig_pie, fig_bar = visualize_limit_up_data(stocks_df, selected_date)
            
            # 显示原始数据表格
            st.subheader("连续涨停股票列表")
            st.dataframe(
                stocks_df[['code', 'name', 'industry', 'limit_up_days']].sort_values('limit_up_days', ascending=False),
                use_container_width=True,
                column_config={
                    'code': '股票代码',
                    'name': '股票名称',
                    'industry': '所属概念',
                    'limit_up_days': '连续涨停天数'
                }
            )
        else:
            st.info(f"{selected_date} 没有连续涨停的股票。")
    
    # AI分析标签页
    with tab2:
        if stocks_df is not None and len(stocks_df) > 0:
            st.subheader("🔍 DeepSeek AI 板块龙头分析")
            st.markdown("""
            点击下方按钮，使用DeepSeek AI对连续涨停股票进行深度分析，包括：
            - 板块分类与龙头识别
            - 龙头股与跟随股分析
            - 市场热点分析
            - 投资策略建议
            """)
            
            # 创建两列布局
            col1, col2 = st.columns([3, 1])
            
            with col1:
                start_analysis = st.button("开始AI分析", key="start_analysis")
            
            # 用于存储分析结果
            if 'analysis_result' not in st.session_state:
                st.session_state.analysis_result = None
                st.session_state.has_analysis = False
            
            # 点击分析按钮时执行
            if start_analysis:
                with st.spinner("DeepSeek AI正在分析行业龙头和跟随股票..."):
                    # 显示原始数据表格
                    st.subheader("连续涨停股票数据")
                    st.dataframe(
                        stocks_df[['code', 'name', 'industry', 'limit_up_days']].sort_values(['industry', 'limit_up_days'], ascending=[True, False]),
                        use_container_width=True,
                        column_config={
                            'code': '股票代码',
                            'name': '股票名称',
                            'industry': '所属概念',
                            'limit_up_days': '连续涨停天数'
                        }
                    )
                    
                    # 获取AI分析结果
                    analysis = analyze_industry_leaders(stocks_df)
                    st.session_state.analysis_result = analysis
                    st.session_state.has_analysis = True
                    
                    # 可视化数据（如果tab1没有执行）
                    if 'fig_pie' not in locals() or 'fig_bar' not in locals():
                        fig_pie, fig_bar = visualize_limit_up_data(stocks_df, selected_date)
                    
                    # 显示分析结果
                    st.subheader("DeepSeek AI 分析结果")
                    st.markdown(analysis)
                    
                    # 添加分析时间戳
                    analysis_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    st.caption(f"分析完成时间: {analysis_time}")
                    
                    # 生成PDF报告 - 不使用Plotly图表对象
                    with st.spinner("正在生成PDF报告..."):
                        pdf_path = generate_pdf_report(
                            stocks_df, 
                            selected_date, 
                            analysis
                        )
                        
                        # 创建下载链接
                        pdf_filename = f"连续涨停分析报告_{selected_date}.pdf"
                        download_link = get_pdf_download_link(pdf_path, pdf_filename)
                        st.markdown(download_link, unsafe_allow_html=True)
            
            # 如果已经有分析结果，但没有点击分析按钮，显示之前的结果
            elif st.session_state.has_analysis:
                # 显示原始数据表格
                st.subheader("连续涨停股票数据")
                st.dataframe(
                    stocks_df[['code', 'name', 'industry', 'limit_up_days']].sort_values(['industry', 'limit_up_days'], ascending=[True, False]),
                    use_container_width=True,
                    column_config={
                        'code': '股票代码',
                        'name': '股票名称',
                        'industry': '所属概念',
                        'limit_up_days': '连续涨停天数'
                    }
                )
                
                # 显示分析结果
                st.subheader("DeepSeek AI 分析结果")
                st.markdown(st.session_state.analysis_result)
                
                # 可视化数据（如果tab1没有执行）
                if 'fig_pie' not in locals() or 'fig_bar' not in locals():
                    fig_pie, fig_bar = visualize_limit_up_data(stocks_df, selected_date)
                
                # 生成PDF报告 - 不使用Plotly图表对象
                with st.spinner("正在生成PDF报告..."):
                    pdf_path = generate_pdf_report(
                        stocks_df, 
                        selected_date, 
                        st.session_state.analysis_result
                    )
                    
                    # 创建下载链接
                    pdf_filename = f"连续涨停分析报告_{selected_date}.pdf"
                    download_link = get_pdf_download_link(pdf_path, pdf_filename)
                    st.markdown(download_link, unsafe_allow_html=True)
            else:
                st.info("点击上方按钮开始AI分析")
        else:
            st.info(f"{selected_date} 没有连续涨停的股票，无法进行分析。")

if __name__ == "__main__":
    main()