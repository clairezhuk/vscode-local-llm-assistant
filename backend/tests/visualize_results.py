import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import glob
import os
import re

INDEX = 6

def parse_results():
    csv_files = glob.glob('results/*.csv')
    if not csv_files:
        print("No CSV files found in results/")
        return None, None, None

    all_data = []
    suite_stats = {}

    for file in csv_files:
        raw_name = os.path.basename(file).replace('.csv', '')
        suite_display = raw_name.replace('_', ' ').title()
        
        df = pd.read_csv(file)
        # Ensure numeric conversion for safety
        df['exec_ok'] = pd.to_numeric(df['exec_ok'], errors='coerce')
        df['test_idx'] = df['id'].apply(lambda x: int(re.findall(r'\d+', x)[-1]))
        df['suite'] = suite_display
        
        # Calculate success_count: 
        # If exec_ok is NaN (theory), success is based on format_ok. 
        # Otherwise, we use the aggregate logic (format AND exec)
        # Note: In the benchmark, we should ideally track 'passed_attempts' directly.
        # Here we assume success_count is the minimum of format and exec per row.
        df['success_count'] = df.apply(
            lambda r: r['format_ok'] if pd.isna(r['exec_ok']) else min(r['format_ok'], r['exec_ok']), 
            axis=1
        )
        
        all_data.append(df)
        
        # Suite Performance Stats
        for mode in ['fast', 'thinking']:
            m_df = df[df['processing_type'] == mode]
            if m_df.empty: continue
            
            total_tests = len(m_df)
            pass_100 = (m_df['success_count'] == m_df['repeats']).sum()
            pass_partial = ((m_df['success_count'] > 0) & (m_df['success_count'] < m_df['repeats'])).sum()
            
            total_attempts = m_df['repeats'].sum()
            total_success_attempts = m_df['success_count'].sum()
            total_failed_attempts = total_attempts - total_success_attempts
            
            # Warning % in failed attempts
            warn_rate = (m_df['warning'].sum() / total_failed_attempts * 100) if total_failed_attempts > 0 else 0
            # Wrong warning % in successful attempts
            wrong_warn_rate = (m_df['wrong_warnings'].sum() / total_success_attempts * 100) if total_success_attempts > 0 else 0
            
            key = f"{suite_display}_{mode}"
            suite_stats[key] = {
                'display': f"{pass_100}/{pass_partial}/{total_tests}",
                'warn_info': f"Warn on Fail: {warn_rate:.1f}% | Wrong Warn: {wrong_warn_rate:.1f}%"
            }

    full_df = pd.concat(all_data)
    
    # Latency: sum(time_s) / sum(repeats)
    latency = full_df.groupby(['processing_type', 'intent']).apply(
        lambda x: x['time_s'].sum() / x['repeats'].sum()
    ).unstack()
    
    return full_df, suite_stats, latency

def create_dashboard():
    df, stats, latency_stats = parse_results()
    if df is None: return

    plt.style.use('dark_background')
    fig = plt.figure(figsize=(22, 12))
    gs = fig.add_gridspec(2, 3, width_ratios=[0.8, 1, 1], height_ratios=[1, 0.15])
    
    ax_text = fig.add_subplot(gs[0, 0])
    ax_fast = fig.add_subplot(gs[0, 1])
    ax_think = fig.add_subplot(gs[0, 2])
    ax_summary = fig.add_subplot(gs[1, :])

    # --- LEFT: Text Stats ---
    ax_text.axis('off')
    y = 0.98
    ax_text.text(0, y, "SUITE PERFORMANCE (100% / Partial / Total)", fontsize=14, fontweight='bold', color='#3498db')
    y -= 0.04
    
    suites = sorted(df['suite'].unique())
    for s_name in suites:
        f_s = stats.get(f"{s_name}_fast", {'display': 'N/A', 'warn_info': ''})
        t_s = stats.get(f"{s_name}_thinking", {'display': 'N/A', 'warn_info': ''})
        
        txt = (f"● {s_name}\n"
               f"  Fast:     {f_s['display']}  ({f_s['warn_info']})\n"
               f"  Thinking: {t_s['display']}  ({t_s['warn_info']})")
        ax_text.text(0.02, y, txt, fontsize=9, verticalalignment='top', family='monospace')
        y -= 0.12

    y -= 0.02
    ax_text.text(0, y, "AVG LATENCY (seconds per attempt)", fontsize=13, fontweight='bold', color='#9b59b6')
    y -= 0.04
    intent_map = {1: 'Theory', 2: 'Coding', 3: 'CLI'}
    for idx, name in intent_map.items():
        try:
            f_l = latency_stats.loc['fast', idx]
            t_l = latency_stats.loc['thinking', idx]
            ax_text.text(0.02, y, f"➤ {name}: {f_l:.2f}s (F) / {t_l:.2f}s (T)", fontsize=10, family='monospace')
            y -= 0.04
        except: pass

    # --- CENTER & RIGHT: Heatmaps ---
    max_tests = df['test_idx'].max()
    fast_mtx = np.zeros((max_tests, len(suites)))
    think_mtx = np.zeros((max_tests, len(suites)))

    for i, suite in enumerate(suites):
        suite_data = df[df['suite'] == suite]
        for _, row in suite_data.iterrows():
            idx = row['test_idx'] - 1
            reps = row['repeats']
            success = row['success_count']
            
            # Value Mapping:
            # 1: Dark Green (100%), 2: Green (>50%), 3: Pale Lime (>0%)
            # 4: Yellow (Fail + Warn), 5: Red (Total Fail), 6: Orange (Logic OK)
            if success == reps:
                val = 1
            elif success > reps / 2:
                val = 2
            elif success > 0:
                val = 3
            else: # success == 0
                if row['warning'] > reps / 2:
                    val = 4
                elif pd.notna(row['exec_ok']) and row['exec_ok'] > reps / 2:
                    val = 6 # Exec (Logic) passed, but Format failed
                else:
                    val = 5 # Execution failed or no logic passed
            
            if row['processing_type'] == 'fast': fast_mtx[idx, i] = val
            else: think_mtx[idx, i] = val

    # Colormap: 0:Empty, 1:DarkG, 2:Green, 3:Lime, 4:Yellow, 5:Red, 6:Orange
    colors = ['#1e1e1e', '#1b5e20', '#2ecc71', '#c0ca33', '#f1c40f', '#e74c3c', '#e67e22']
    cmap = plt.matplotlib.colors.ListedColormap(colors)

    for ax, mtx, title, clr in [(ax_fast, fast_mtx, "FAST MODE", '#2ecc71'), 
                                (ax_think, think_mtx, "THINKING MODE", '#f1c40f')]:
        ax.imshow(mtx, cmap=cmap, aspect='auto', vmin=0, vmax=6)
        ax.set_title(title, fontsize=14, color=clr, fontweight='bold')
        ax.set_xticks(np.arange(len(suites)))
        ax.set_xticklabels([s.split(' ')[0] for s in suites], fontsize=9)
        ax.set_yticks(np.arange(max_tests))
        ax.set_yticklabels(np.arange(1, max_tests + 1), fontsize=8)
        ax.grid(which='both', color='#333333', linestyle='-', linewidth=0.5)

    # Legends
    patches = [
        mpatches.Patch(color='#1b5e20', label='100% Pass'),
        mpatches.Patch(color='#2ecc71', label='>50% Pass'),
        mpatches.Patch(color='#c0ca33', label='Part. Pass'),
        mpatches.Patch(color='#e74c3c', label='Fail'),
        mpatches.Patch(color='#e67e22', label='Logic OK'),
        mpatches.Patch(color='#f1c40f', label='Fail+Warn')
    ]
    ax_think.legend(handles=patches, loc='upper center', bbox_to_anchor=(-0.1, -0.05), ncol=3, fontsize=9)

    # --- BOTTOM: Global Summary ---
    ax_summary.axis('off')
    
    def get_summary(mode):
        m_df = df[df['processing_type'] == mode]
        t_100 = (m_df['success_count'] == m_df['repeats']).sum()
        t_part = ((m_df['success_count'] > 0) & (m_df['success_count'] < m_df['repeats'])).sum()
        return f"{t_100} / {t_part} / {len(m_df)}"

    summary_text = (
        f"GLOBAL (100% / Partial / Total)\n"
        f"FAST: {get_summary('fast')}   |   THINKING: {get_summary('thinking')}"
    )
    ax_summary.text(0.5, 0.4, summary_text, fontsize=18, fontweight='bold', ha='center', 
                    family='monospace', bbox=dict(facecolor='#000', edgecolor='#3498db', boxstyle='round,pad=1'))

    plt.tight_layout()
    plt.savefig(f'results/dashboard_v{INDEX}.png', dpi=150)
    print(f"Dashboard saved to results/dashboard_v{INDEX}.png")

if __name__ == "__main__":
    create_dashboard()