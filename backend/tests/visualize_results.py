import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import glob
import os
import re

def parse_results():
    csv_files = glob.glob('results/*.csv')
    if not csv_files:
        print("No CSV files found in results/")
        return None, None, None

    all_data = []
    suite_stats = {}

    for file in csv_files:
        suite_name = os.path.basename(file).replace('.csv', '').split('_')[0]
        df = pd.read_csv(file)
        
        # Визначаємо статус
        def determine_status(row):
            if str(row['intent_ok']).lower() == 'false': return 2
            exec_val = str(row['exec_ok']).lower()
            format_val = str(row['format_ok']).lower()
            if exec_val == 'false' or format_val == 'false': return 3
            return 1

        df['status'] = df.apply(determine_status, axis=1)
        df['suite'] = suite_name
        df['test_num'] = df['id'].apply(lambda x: int(re.findall(r'\d+', x)[-1]))
        
        all_data.append(df)
        
        suite_stats[suite_name] = {
            'total': len(df),
            'passed': len(df[df['status'] == 1]),
            'intent_err': len(df[df['status'] == 2]),
            'fail': len(df[df['status'] == 3])
        }

    full_df = pd.concat(all_data)
    
    # Розрахунок середнього часу по інтентах
    # 1: text, 2: code, 3: cli
    intent_map = {1: 'Theory (Text)', 2: 'Coding (Code)', 3: 'Terminal (CLI)'}
    time_stats = {}
    for i_type in [1, 2, 3]:
        subset = full_df[full_df['true_intent'] == i_type]
        if not subset.empty:
            time_stats[intent_map[i_type]] = subset['time_s'].mean()
        else:
            time_stats[intent_map[i_type]] = 0.0

    return full_df, suite_stats, time_stats

def create_dashboard():
    df, stats, time_stats = parse_results()
    if df is None: return

    plt.style.use('dark_background')
    # Збільшуємо висоту фігури для вертикальної таблиці
    fig = plt.figure(figsize=(14, 14))
    
    # Співвідношення: ліва колонка ширша для тексту, права для вузької витягнутої таблиці
    gs = fig.add_gridspec(2, 2, width_ratios=[1.2, 1], height_ratios=[1, 0.08])
    
    ax_text = fig.add_subplot(gs[0, 0])
    ax_table = fig.add_subplot(gs[0, 1])
    ax_summary = fig.add_subplot(gs[1, :])

    # --- ЛІВА ЧАСТИНА: Статистика ---
    ax_text.axis('off')
    y_pos = 0.98
    
    # Блок успішності по сюїтах
    ax_text.text(0, y_pos, "SUITE PERFORMANCE", fontsize=16, fontweight='bold', color='#3498db')
    y_pos -= 0.05
    
    total_all, passed_all = 0, 0
    for suite in sorted(stats.keys()):
        s = stats[suite]
        total_all += s['total']
        passed_all += s['passed']
        
        suite_text = (f"● {suite}:\n"
                      f"  Status: {s['passed']}/{s['total']} passed\n"
                      f"  Fails: [Intent: {s['intent_err']}, Logic: {s['fail']}]")
        
        ax_text.text(0.02, y_pos, suite_text, fontsize=11, verticalalignment='top', family='monospace')
        y_pos -= 0.12 # Збільшений інтервал

    # Блок аналізу часу
    y_pos -= 0.05
    ax_text.text(0, y_pos, "AVERAGE LATENCY BY INTENT", fontsize=16, fontweight='bold', color='#9b59b6')
    y_pos -= 0.05
    
    for intent_name, avg_time in time_stats.items():
        time_text = f"➤ {intent_name}: {avg_time:.2f} seconds"
        ax_text.text(0.02, y_pos, time_text, fontsize=12, verticalalignment='top', family='monospace')
        y_pos -= 0.06

    # --- ПРАВА ЧАСТИНА: Витягнута таблиця ---
    suites = sorted(df['suite'].unique())
    max_test = 25 # Фіксуємо на 25 за вашим запитом
    
    matrix = np.zeros((max_test, len(suites)))
    for i, suite in enumerate(suites):
        suite_df = df[df['suite'] == suite]
        for _, row in suite_df.iterrows():
            if row['test_num'] <= max_test:
                matrix[row['test_num']-1, i] = row['status']

    cmap = plt.matplotlib.colors.ListedColormap(['#1e1e1e', '#2ecc71', '#f1c40f', '#e74c3c'])
    im = ax_table.imshow(matrix, cmap=cmap, aspect='auto', interpolation='nearest')
    
    # Решітка та підписи
    ax_table.set_xticks(np.arange(len(suites)))
    ax_table.set_xticklabels(suites, fontsize=10, fontweight='bold')
    ax_table.set_yticks(np.arange(max_test))
    ax_table.set_yticklabels(np.arange(1, max_test + 1))
    ax_table.set_title("Test Map (1-25)", fontsize=14, pad=20)
    
    # Додаємо сітку для чіткості квадратиків
    ax_table.set_xticks(np.arange(-.5, len(suites), 1), minor=True)
    ax_table.set_yticks(np.arange(-.5, max_test, 1), minor=True)
    ax_table.grid(which='minor', color='#333333', linestyle='-', linewidth=1)

    # Легенда під таблицею
    patches = [
        mpatches.Patch(color='#2ecc71', label='Success'),
        mpatches.Patch(color='#f1c40f', label='Wrong Intent'),
        mpatches.Patch(color='#e74c3c', label='Logic Fail'),
        mpatches.Patch(color='#1e1e1e', label='N/A')
    ]
    ax_table.legend(handles=patches, loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=2, fontsize=9)

    # --- НИЖНЯ ЧАСТИНА: Підсумок ---
    ax_summary.axis('off')
    success_rate = (passed_all / total_all) * 100 if total_all > 0 else 0
    summary_text = f"TOTAL: {passed_all} / {total_all} PASSED ({success_rate:.1f}%)"
    
    color = '#2ecc71' if success_rate > 80 else '#f1c40f' if success_rate > 50 else '#e74c3c'
    ax_summary.text(0.5, 0.5, summary_text, fontsize=22, fontweight='bold', 
                    color=color, ha='center', va='center', 
                    bbox=dict(facecolor='#000', edgecolor=color, boxstyle='round,pad=0.5', linewidth=2))

    plt.tight_layout(rect=[0, 0, 1, 0.98])
    plt.savefig('results/dashboard.png', dpi=150, bbox_inches='tight')
    print(f"\n[Dashboard] Success! Average time for Code: {time_stats['Coding (Code)']:.2f}s")
    plt.show()

if __name__ == "__main__":
    create_dashboard()