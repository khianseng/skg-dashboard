import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import timedelta
import numpy as np

# --- 1. 页面配置 ---
st.set_page_config(
    page_title="SKG Dashboard (Live Data)",
    page_icon="📊",
    layout="wide"
)

# --- 2. 简易登录 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    def password_entered():
        # 从 st.secrets 中读取账号和密码
        if (st.session_state["username"] == st.secrets["DB_USERNAME"] and 
            st.session_state["password"] == st.secrets["DB_PASSWORD"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.subheader("Login / 登入")
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    return True

if not check_password():
    st.stop()

# --- 3. 数据加载 (Robust Loading) ---
@st.cache_data
def load_data():
    file_path = 'skg_data.xlsx'
    try:
        xls = pd.ExcelFile(file_path)
        sheet_names = xls.sheet_names
        
        # 自动寻找包含关键字的 Sheet (防止名字只有一点点不一样)
        stock_sheet = next((s for s in sheet_names if "stock" in s.lower()), None)
        sales_sheet = next((s for s in sheet_names if "sales" in s.lower()), None)

        if stock_sheet and sales_sheet:
            df_stock = pd.read_excel(file_path, sheet_name=stock_sheet)
            df_sales = pd.read_excel(file_path, sheet_name=sales_sheet)
            
            # --- 关键：统一列名格式 (去除空格) ---
            # 这样 'AR Type ' 也能被识别为 'AR Type'
            df_stock.columns = df_stock.columns.str.strip()
            df_sales.columns = df_sales.columns.str.strip()
            
            return df_stock, df_sales
        else:
            st.error(f"无法自动识别 Sheet。检测到的 Sheet 名称: {sheet_names}")
            return pd.DataFrame(), pd.DataFrame()
            
    except FileNotFoundError:
        st.error("找不到 skg_data.xlsx 文件。")
        return pd.DataFrame(), pd.DataFrame()

df_stock_raw, df_sales_raw = load_data()

if df_stock_raw.empty or df_sales_raw.empty:
    st.stop()

# --- 4. 数据预处理 (更简单了) ---

# 4.1 处理 Sales Data
df_sales = df_sales_raw.copy()
df_sales['Date'] = pd.to_datetime(df_sales['Date'])

# 自动提取产品类别 (保留这个功能，因为Excel通常没有Category列)
def extract_category(stock_name):
    name = str(stock_name).lower()
    if 'eye' in name: return 'Eye Massager'
    if 'neck' in name or 'cervical' in name: return 'Neck/Cervical'
    if 'waist' in name: return 'Waist Massager'
    if 'knee' in name: return 'Knee Massager'
    if 'gun' in name or 'fascia' in name: return 'Massage Gun'
    if 'body' in name or 'fascia' in name: return 'Body Massager'
    return 'Others'

df_sales['Category'] = df_sales['Stock Name'].apply(extract_category)

# 4.2 处理 Stock Data
df_stock = df_stock_raw.copy()
# 确保 Warehouse Type 存在，如果不存在填 Unknown
if 'Warehouse Type' not in df_stock.columns:
    df_stock['Warehouse Type'] = 'Unknown' 
else:
    df_stock['Warehouse Type'] = df_stock['Warehouse Type'].fillna('Unknown')


# --- 5. 侧边栏过滤器 ---
st.sidebar.title("Filters")

# 获取数据中的最新日期作为基准
latest_date_in_data = df_sales['Date'].max()
first_day_of_current_month = latest_date_in_data.replace(day=1)

# 主日期范围 (Primary Date Range)
date_range = st.sidebar.date_input(
    "Primary Date Range", 
    value=(first_day_of_current_month.date(), latest_date_in_data.date()),
    min_value=df_sales['Date'].min().date(),
    max_value=df_sales['Date'].max().date()
)

# --- 全局对比控制 ---
st.sidebar.divider()
enable_comparison = st.sidebar.checkbox("Enable Comparison", value=True)

comp_range = None
if enable_comparison:
    # 自动推算上一个等长周期作为默认对比值
    d1, d2 = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    duration = (d2 - d1).days + 1
    prev_end = d1 - timedelta(days=1)
    prev_start = prev_end - timedelta(days=duration - 1)
    
    comp_range = st.sidebar.date_input(
        "Comparison Date Range",
        value=(prev_start.date(), prev_end.date()),
        key='global_comp_date'
    )

# --- 6. 主面板 ---
st.title("SKG Business Analytics")
tab1, tab2, tab3 = st.tabs(["📦 Stock Balance", "📈 Sales Analysis", "🛒 Purchase (DOS)"])

# === TAB 1: STOCK ===
with tab1:
    st.header("Inventory Overview")
    
    # --- 1. 过滤器 ---
    with st.expander("🔎 Filter Options (Click to expand)", expanded=False):
        selected_wh_types = st.multiselect(
            "Select Warehouse Types:",
            options=df_stock['Warehouse Type'].unique(),
            default=df_stock['Warehouse Type'].unique()
        )
    
    filtered_stock = df_stock[df_stock['Warehouse Type'].isin(selected_wh_types)]

    if filtered_stock.empty:
        st.warning("Please select at least one Warehouse Type.")
    else:
        # --- 2. 核心分析区 (左图 - 空隙 - 右表) ---
        summary_df = filtered_stock.groupby('Warehouse Type')['Quantity'].sum().reset_index()
        summary_df = summary_df.sort_values('Quantity', ascending=False)
        
        total_qty = summary_df['Quantity'].sum()
        summary_df['% Share'] = (summary_df['Quantity'] / total_qty * 100).apply(lambda x: f"{x:.1f}%")
        
        # [修改点]：这里创建了 3 个列
        # 1.5 是左边图的宽度
        # 0.2 是中间的空隙 (你可以把这个数字改大改小来调整间距)
        # 1.0 是右边表的宽度
        col_pie, col_spacer, col_table = st.columns([1, 0.2, 1]) 
        
        # [左] 饼图
        with col_pie:
            st.subheader("Distribution")
            fig_pie = px.pie(
                filtered_stock, 
                values='Quantity', 
                names='Warehouse Type', 
                hole=0.5,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        # [中] 空隙列什么都不放，自然形成留白
            
        # [右] 汇总表格
        with col_table:
            st.subheader("Balance Summary")
            st.metric(label="Total Selected Stock", value=f"{total_qty:,.0f}")
            
            st.dataframe(
                summary_df,
                hide_index=True,
                use_container_width=True,
                height=300,
                column_config={
                    "Warehouse Type": "Type",
                    "Quantity": st.column_config.ProgressColumn(
                        "Stock Qty", 
                        format="%d", 
                        min_value=0, 
                        max_value=int(summary_df['Quantity'].max())
                    ),
                    "% Share": st.column_config.TextColumn("Share")
                }
            )

        st.divider()

        # --- 3. Top SKUs (移到第二行，宽屏显示) ---
        st.subheader(f"Top 20 SKUs")
        
        # 这里改成 nlargest(20)
        top_stock = filtered_stock.groupby('Stock Name')['Quantity'].sum().nlargest(20).reset_index().sort_values('Quantity', ascending=True)
        
        fig_bar = px.bar(
            top_stock, 
            x='Quantity', 
            y='Stock Name', 
            orientation='h',
            text_auto=True,
            color='Quantity',
            color_continuous_scale='Blues'
        )
        # 高度增加到 600，保证显示20个不拥挤
        fig_bar.update_layout(xaxis_title=None, yaxis_title=None, height=600)
        st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        # --- 4. 细节卡片区 (保持不变) ---
        st.subheader("Warehouse & Outlet Details")
        
        grid_cols = st.columns(3)
        active_types = summary_df['Warehouse Type'].tolist()
        card_count = 0
        
        for wh_type in active_types:
            type_data = filtered_stock[filtered_stock['Warehouse Type'] == wh_type]
            breakdown = type_data.groupby('Warehouse Name')['Quantity'].sum().reset_index()
            breakdown = breakdown[breakdown['Quantity'] > 0]
            
            if breakdown.empty:
                continue
            
            breakdown = breakdown.sort_values('Quantity', ascending=False)
            type_total = breakdown['Quantity'].sum()
            
            with grid_cols[card_count % 3]:
                with st.container(border=True):
                    st.markdown(f"**{wh_type}**")
                    st.markdown(f"### {type_total:,.0f}")
                    
                    st.dataframe(
                        breakdown,
                        hide_index=True,
                        use_container_width=True,
                        height=200,
                        column_config={
                            "Warehouse Name": st.column_config.TextColumn("Location"),
                            # [修改点]：这里也加上了 ProgressColumn，视觉更统一
                            "Quantity": st.column_config.ProgressColumn(
                                "Qty", 
                                format="%d",
                                min_value=0,
                                max_value=int(breakdown['Quantity'].max()) if not breakdown.empty else 100
                            )
                        }
                    )
            card_count += 1

# === TAB 2: SALES ===
with tab2:
    st.header("Sales Performance Analysis")
    
    # --- 1. 顶部变量初始化 (核心修复：防止 NameError) ---
    all_range_dates = []
    df_trend_base = pd.DataFrame()
    sorted_months_list = []

    # --- 2. Filter Area (仅保留 Warehouse) ---
    with st.expander("🔎 Filter by Warehouse", expanded=False):
        all_warehouses = df_sales['Warehouse'].unique()
        selected_warehouses_sales = st.multiselect(
            "Select Warehouses:",
            options=all_warehouses,
            default=all_warehouses,
            key='sales_warehouse_filter'
        )
            
    # --- 3. 数据预处理与核心逻辑 ---
    # A. 基础清洗 (防止分类/排序报错)
    df_sales['AR Type'] = df_sales['AR Type'].fillna("Unknown").astype(str)
    df_sales['Stock Name'] = df_sales['Stock Name'].fillna("Unknown").astype(str)
    
    # B. 确定全局日期范围 (用于 Sparklines 提取不重复且连续的趋势)
    if len(date_range) == 2:
        all_range_dates.extend([pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])])
    if enable_comparison and comp_range and len(comp_range) == 2:
        all_range_dates.extend([pd.to_datetime(comp_range[0]), pd.to_datetime(comp_range[1])])

    if all_range_dates:
        start_full = min(all_range_dates)
        end_full = max(all_range_dates)
        # 核心逻辑：直接从原始数据提取全范围，用于绘制趋势线
        mask_full = (
            (df_sales['Date'] >= start_full) & 
            (df_sales['Date'] <= end_full) & 
            (df_sales['Warehouse'].isin(selected_warehouses_sales))
        )
        df_trend_base = df_sales[mask_full].copy()
        df_trend_base['Month_Label'] = df_trend_base['Date'].dt.to_period('M').astype(str)
        sorted_months_list = sorted(df_trend_base['Month_Label'].unique())

    # C. 当前周期数据 (用于 Section 1 & 2 & 3)
    mask_curr = (
        (df_sales['Date'] >= pd.to_datetime(date_range[0])) & 
        (df_sales['Date'] <= pd.to_datetime(date_range[1])) &
        (df_sales['Warehouse'].isin(selected_warehouses_sales))
    )
    df_curr = df_sales[mask_curr].copy()

    # D. 全局对比数据准备 (用于 Section 3)
    df_comp_sidebar = pd.DataFrame()
    if enable_comparison and comp_range and len(comp_range) == 2:
        mask_comp = (
            (df_sales['Date'] >= pd.to_datetime(comp_range[0])) & 
            (df_sales['Date'] <= pd.to_datetime(comp_range[1])) &
            (df_sales['Warehouse'].isin(selected_warehouses_sales))
        )
        df_comp_sidebar = df_sales[mask_comp].copy()

    # E. 合并侧边栏选中的数据用于 Section 3 柱状图
    df_all_chan = pd.concat([df_comp_sidebar, df_curr], ignore_index=True)
    if not df_all_chan.empty:
        df_all_chan['Month'] = df_all_chan['Date'].dt.to_period('M').astype(str)
        sorted_months_chan = sorted(df_all_chan['Month'].unique())
    
    # --- 4. 渲染逻辑 ---
    if df_curr.empty:
        st.warning("No sales data found for the primary selected range.")
    else:
        # =========================================================
        # PART 1: KPI Summary (仅显示当前周期)
        # =========================================================
        total_sales = df_curr['Sales'].sum()
        total_qty = df_curr['Quantity'].sum()
        avg_order = total_sales / len(df_curr) if len(df_curr) > 0 else 0
        
        k1, k2, k3 = st.columns(3)
        k1.metric("💰 Total Revenue", f"RM{total_sales:,.2f}")
        k2.metric("📦 Units Sold", f"{total_qty:,.0f}")
        k3.metric("🧾 Avg. Ticket Size", f"RM{avg_order:,.2f}")
        
        st.divider()

        # =========================================================
        # PART 2: Overall Company Trend (仅显示当前周期)
        # =========================================================
        st.subheader("1. Overall Company Trend")
        trend_view = st.radio("Time Grouping:", ["Monthly", "Weekly"], horizontal=True, key='trend_view_radio')
        freq = 'M' if trend_view == "Monthly" else 'W'
        
        trend_df = df_curr.copy()
        trend_df['Sort_Key'] = trend_df['Date'].dt.to_period(freq).dt.start_time
        trend_df['DP'] = trend_df['Date'].dt.to_period(freq).astype(str)
        trend_data = trend_df.groupby(['Sort_Key', 'DP'])['Sales'].sum().reset_index().sort_values('Sort_Key')
        
        fig_overall = px.line(trend_data, x='DP', y='Sales', markers=True, text='Sales')
        fig_overall.update_traces(textposition="top center", texttemplate='%{text:.2s}', line_color='#1f77b4', line_width=3)
        fig_overall.update_layout(height=350, xaxis_title="Time Period", yaxis_title="Revenue (RM)")
        st.plotly_chart(fig_overall, use_container_width=True)

        st.divider()

        # =========================================================
        # PART 3: Warehouse Comparison (Section 2)
        # =========================================================
        st.subheader("2. Warehouse Comparison Breakdown")
        wh_comp_df = trend_df.groupby(['Sort_Key', 'DP', 'Warehouse'])['Sales'].sum().reset_index().sort_values('Sort_Key')
        chart_type = st.selectbox("Select Visualization Style:", ["Heatmap (Best for Overview)", "Small Charts (Best for Individual Trend)", "Multi-Line (Original)"], index=0, key='wh_view_select')
        period_order = trend_data['DP'].unique()

        if chart_type == "Heatmap (Best for Overview)":
            fig_wh = px.density_heatmap(wh_comp_df, x='DP', y='Warehouse', z='Sales', histfunc="sum", color_continuous_scale="Viridis", text_auto=True)
            fig_wh.update_layout(xaxis=dict(type='category', categoryorder='array', categoryarray=period_order), height=500)
            st.plotly_chart(fig_wh, use_container_width=True)
        elif chart_type == "Small Charts (Best for Individual Trend)":
            fig_wh = px.line(wh_comp_df, x='DP', y='Sales', color='Warehouse', facet_col='Warehouse', facet_col_wrap=3, markers=True)
            fig_wh.update_yaxes(matches=None)
            fig_wh.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
            st.plotly_chart(fig_wh, use_container_width=True)
        else:
            fig_wh = px.line(wh_comp_df, x='DP', y='Sales', color='Warehouse', markers=True)
            fig_wh.update_layout(xaxis=dict(type='category', categoryorder='array', categoryarray=period_order), height=450)
            st.plotly_chart(fig_wh, use_container_width=True)

        st.divider()

        # =========================================================
        # PART 4: Channel & Customer Analysis (Section 3 - 支持多月份对比)
        # =========================================================
        st.subheader("3. Channel & Customer Analysis")
        ar_col1, col_spacer, ar_col2 = st.columns([1, 0.1, 1])
        
        with ar_col1:
            st.caption("📊 Monthly Revenue Breakdown by Channel (Comparison Mode)")
            chan_data = df_all_chan.groupby(['AR Type', 'Month'])['Sales'].sum().reset_index()
            fig_ar = px.bar(chan_data, x='AR Type', y='Sales', color='Month', barmode='group', text_auto='.2s', category_orders={"Month": sorted_months_chan}, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_ar.update_layout(height=450, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_ar, use_container_width=True)
            
        with ar_col2:
            st.caption("🏆 Top Customers (Full Selected Range)")
            cust_detail = df_all_chan.groupby(['AR Type', 'AR Name'])['Sales'].sum().reset_index().sort_values('Sales', ascending=False).head(50)
            st.dataframe(cust_detail, hide_index=True, use_container_width=True, height=400)

        st.divider()
        
        # =========================================================
        # PART 5: Product Performance & Sparklines (Section 4)
        # =========================================================
        st.subheader("4. Product Performance & Trend Analysis")
        
        # --- A. 获取“当月”和“上月”的周期 ---
        curr_month_period = pd.to_datetime(date_range[1]).to_period('M')
        prev_month_period = curr_month_period - 1

        # --- B. 准备快照数据 (饼图和 Top 5) ---
        p_top_col1, col_spacer_p, p_top_col2 = st.columns([1, 0.1, 1])
        with p_top_col1:
            st.caption(f"📊 Sales by Category ({curr_month_period})")
            cat_sales = df_sales[
                (df_sales['Date'].dt.to_period('M') == curr_month_period) & 
                (df_sales['Warehouse'].isin(selected_warehouses_sales))
            ].groupby('Category')['Sales'].sum().reset_index().sort_values('Sales', ascending=False)
            fig_cat = px.pie(cat_sales, values='Sales', names='Category', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_cat.update_layout(height=350, margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig_cat, use_container_width=True)

        with p_top_col2:
            st.caption(f"🏆 Top Selling Models ({curr_month_period})")
            top_m = df_sales[
                (df_sales['Date'].dt.to_period('M') == curr_month_period) & 
                (df_sales['Warehouse'].isin(selected_warehouses_sales))
            ].groupby(['Stock Name', 'Category'])[['Quantity', 'Sales']].sum().reset_index().sort_values('Quantity', ascending=False).head(5)
            
            if not top_m.empty:
                st.dataframe(
                    top_m[['Stock Name', 'Category', 'Quantity', 'Sales']], 
                    use_container_width=True, hide_index=True, height=250, 
                    column_config={
                        "Category": st.column_config.TextColumn("Category", width="small"), 
                        "Stock Name": st.column_config.TextColumn("Model Name", width="medium"), 
                        "Quantity": st.column_config.ProgressColumn("Units", format="%d", max_value=int(top_m['Quantity'].max())), 
                        "Sales": st.column_config.NumberColumn(format="RM%.2f")
                    }
                )

        st.divider()

        # --- C. 下层：迷你趋势线表格 (优化全量历史趋势) ---
        st.caption("📈 Top 20 Models Performance with Sparklines")
        
        # 1. 准备【不受过滤影响】的趋势线列表
        df_full_history = df_sales[
            (df_sales['Date'].dt.to_period('M') <= curr_month_period) & 
            (df_sales['Warehouse'].isin(selected_warehouses_sales))
        ].copy()
        df_full_history['Month_Label'] = df_full_history['Date'].dt.to_period('M').astype(str)
        
        full_months_axis = sorted(df_full_history['Month_Label'].unique())
        
        spark_raw = df_full_history.groupby(['Stock Name', 'Month_Label'])['Quantity'].sum().reset_index()
        spark_pivot = spark_raw.pivot(index='Stock Name', columns='Month_Label', values='Quantity').fillna(0)
        
        # 核心：确保趋势数据包含了完整的历史月份轴
        spark_pivot['Trend'] = spark_pivot.values.tolist()
        spark_pivot = spark_pivot.reset_index()

        # 2. 计算本月和上月 Qty
        p_curr = df_sales[
            (df_sales['Date'].dt.to_period('M') == curr_month_period) & 
            (df_sales['Warehouse'].isin(selected_warehouses_sales))
        ].groupby('Stock Name')['Quantity'].sum().reset_index().rename(columns={'Quantity':'Current'})

        p_prev = df_sales[
            (df_sales['Date'].dt.to_period('M') == prev_month_period) & 
            (df_sales['Warehouse'].isin(selected_warehouses_sales))
        ].groupby('Stock Name')['Quantity'].sum().reset_index().rename(columns={'Quantity':'Previous'})
        
        # 3. 合并数据并重新排列列顺序
        final_table = pd.merge(p_curr, p_prev, on='Stock Name', how='left').fillna(0)
        final_table = pd.merge(final_table, spark_pivot[['Stock Name', 'Trend']], on='Stock Name', how='left')
        
        # 计算增长率
        final_table['Growth %'] = ((final_table['Current'] - final_table['Previous']) / final_table['Previous'] * 100).replace([np.inf, -np.inf], 0)

        # 【关键修改】：按照你要求的顺序排列 DataFrame 列
        # 顺序：Model Name (Stock Name) -> Current -> Previous -> Growth % -> Trend
        order_columns = ['Stock Name', 'Current', 'Previous', 'Growth %', 'Trend']
        display_df = final_table.sort_values('Current', ascending=False).head(20)[order_columns]

        # --- D. 定义高亮函数 ---
        def color_growth(val):
            if val < 0:
                return 'color: #ff4b4b; font-weight: bold;' # 红色
            elif val > 0:
                return 'color: #09ab3b; font-weight: bold;' # 绿色
            return 'color: gray;'

        # 应用样式
        styled_df = display_df.style.map(color_growth, subset=['Growth %'])

        # 4. 渲染表格
        st.data_editor(
            styled_df,
            use_container_width=True, hide_index=True, height=800,
            column_config={
                "Stock Name": st.column_config.TextColumn("Model Name", width="medium"),
                "Current": st.column_config.NumberColumn(f"Qty ({curr_month_period})", format="%d"),
                "Previous": st.column_config.NumberColumn(f"Qty ({prev_month_period})", format="%d"),
                "Growth %": st.column_config.NumberColumn("Growth", format="%.1f%%"),
                "Trend": st.column_config.AreaChartColumn(
                    "Full History Trend", 
                    width="medium",
                    y_min=0, 
                    help=f"Continuous trend from {full_months_axis[0]} up to {curr_month_period}"
                )
            },
            disabled=True 
        )

# === TAB 3: DOS (Purchase) ===
with tab3:
    st.header("Inventory Health & DOS Analysis")
    st.markdown("💡 **Logic**: `DOS = Current Stock / Average Daily Sales (Past 21 Days)`")
    
    # --- 1. 数据计算逻辑 ---
    last_date = df_sales['Date'].max()
    start_date = last_date - timedelta(days=21)
    recent_sales = df_sales[(df_sales['Date'] > start_date) & (df_sales['Date'] <= last_date)]
    
    # 计算 ADS (日均销量)
    sku_sales = recent_sales.groupby('Stock Code')['Quantity'].sum().reset_index()
    sku_sales['ADS'] = sku_sales['Quantity'] / 21
    
    # 获取当前库存
    sku_stock = df_stock.groupby(['Stock Code', 'Stock Name'])['Quantity'].sum().reset_index()
    
    # 合并数据
    dos_df = pd.merge(sku_stock, sku_sales[['Stock Code', 'ADS']], on='Stock Code', how='left')
    dos_df['ADS'] = dos_df['ADS'].fillna(0)
    
    # --- 2. 定义健康状态 (Indicators) ---
    def get_status(row):
        stock = row['Quantity']
        ads = row['ADS']
        
        if stock <= 0:
            return "⚪ Out of Stock"
        
        if ads == 0:
            return "⚫ Dead Stock (No Sales)"
            
        dos = stock / ads
        
        if dos < 14:
            return "🔴 Low Stock (<14 Days)"
        elif dos > 60:
            return "🟡 Overstock (>60 Days)"
        else:
            return "🟢 Healthy (14-60 Days)"

    dos_df['Status'] = dos_df.apply(get_status, axis=1)
    dos_df['DOS (Days)'] = np.where(dos_df['ADS'] > 0, dos_df['Quantity'] / dos_df['ADS'], 9999)

    # --- 3. 顶部 KPI 指标 (Summary Metrics) ---
    status_counts = dos_df['Status'].value_counts()
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("🔴 Restock Needed", f"{status_counts.get('🔴 Low Stock (<14 Days)', 0)} SKUs")
    with m2:
        st.metric("🟢 Healthy Stock", f"{status_counts.get('🟢 Healthy (14-60 Days)', 0)} SKUs")
    with m3:
        st.metric("🟡 Overstock Alert", f"{status_counts.get('🟡 Overstock (>60 Days)', 0)} SKUs")
    with m4:
        st.metric("⚫ Dead Stock", f"{status_counts.get('⚫ Dead Stock (No Sales)', 0)} SKUs")

    st.divider()

    # --- 4. 过滤器 (全宽) ---
    # 修改：直接写 st.multiselect，不放在 columns 里，这样它就会自动拉宽到由左至右
    filter_status = st.multiselect(
        "Filter by Health Status:",
        options=["🔴 Low Stock (<14 Days)", "🟢 Healthy (14-60 Days)", "🟡 Overstock (>60 Days)", "⚫ Dead Stock (No Sales)", "⚪ Out of Stock"],
        default=["🔴 Low Stock (<14 Days)", "🟢 Healthy (14-60 Days)", "🟡 Overstock (>60 Days)", "⚫ Dead Stock (No Sales)", "⚪ Out of Stock"] 
    )
    
    # 过滤数据
    if filter_status:
        view_df = dos_df[dos_df['Status'].isin(filter_status)]
    else:
        view_df = dos_df 

    # 排序优化
    view_df = view_df.sort_values(by=['DOS (Days)', 'ADS'], ascending=[True, False])

    # --- 5. 详细表格 (变长) ---
    st.subheader("Detailed DOS Table")
    
    # 修改：增加了 height=800，让表格变得很长
    st.dataframe(
        view_df[['Status', 'Stock Name', 'Quantity', 'ADS', 'DOS (Days)']],
        use_container_width=True,
        hide_index=True,
        height=800,  # <--- 这里控制高度，800像素大概能显示 20-25 行
        column_config={
            "Status": st.column_config.TextColumn("Health Status", width="medium"),
            "Stock Name": st.column_config.TextColumn("Product Name", width="large"),
            "Quantity": st.column_config.NumberColumn("Current Stock", format="%d"),
            "ADS": st.column_config.NumberColumn("Avg Daily Sales", format="%.2f"),
            "DOS (Days)": st.column_config.NumberColumn(
                "Est. Days Left", 
                format="%.1f"
            )
        }
    )