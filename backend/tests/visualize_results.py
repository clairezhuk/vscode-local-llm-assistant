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
        raw_name = os.path.basename(file).replace('.csv', '')
        # Format suite name: L1 (basic algorithms)
        suite_display = raw_name.replace('_', ' ').replace('L', 'L', 1)
        
        df = pd.read_csv(file)
        # Extract last 3 digits for sorting
        df['test_idx'] = df['id'].apply(lambda x: int(re.findall(r'\d+', x)[-1]))
        df['suite'] = suite_display
        all_data.append(df)
        
        # Calculate suite-level stats
        fast_df = df[df['processing_type'] == 'fast']
        think_df = df[df['processing_type'] == 'thinking']
        
        def is_passed(row):
            f_ok = str(row['format_ok']).lower() == 'true'
            # exec_ok can be NaN for non-code tasks
            e_ok = str(row['exec_ok']).lower() != 'false'
            return f_ok and e_ok

        f_passed = fast_df.apply(is_passed, axis=1).sum()
        t_passed_mask = think_df.apply(is_passed, axis=1)
        t_passed = t_passed_mask.sum()
        
        # Count warnings only for failed thinking tests
        t_fails = think_df[~t_passed_mask]
        t_warnings = str(t_fails['warning']).lower().count('true')

        suite_stats[suite_display] = {
            'fast_pass': f_passed, 'fast_total': len(fast_df),
            'think_pass': t_passed, 'think_total': len(think_df),
            'think_warn': t_warnings
        }

    full_df = pd.concat(all_data)
    
    # Calculate Latency by mode and intent
    latency = full_df.groupby(['processing_type', 'intent'])['time_s'].mean().unstack()
    return full_df, suite_stats, latency

def create_dashboard():
    df, stats, latency_stats = parse_results()
    if df is None: return

    plt.style.use('dark_background')
    fig = plt.figure(figsize=(20, 14))
    gs = fig.add_gridspec(2, 3, width_ratios=[0.8, 1, 1], height_ratios=[1, 0.1])
    
    ax_text = fig.add_subplot(gs[0, 0])
    ax_fast = fig.add_subplot(gs[0, 1])
    ax_think = fig.add_subplot(gs[0, 2])
    ax_summary = fig.add_subplot(gs[1, :])

    # --- LEFT COLUMN: Performance Text ---
    ax_text.axis('off')
    y = 0.98
    ax_text.text(0, y, "SUITE PERFORMANCE", fontsize=16, fontweight='bold', color='#3498db')
    y -= 0.05
    
    for s_name in sorted(stats.keys()):
        s = stats[s_name]
        t_fail = s['think_total'] - s['think_pass']
        suite_txt = (f"● {s_name}\n"
                     f"  Fast: {s['fast_pass']}/{s['fast_total']} passed\n"
                     f"  Thinking: {s['think_pass']}/{s['think_total']} passed (warns {s['think_warn']}/{t_fail})")
        ax_text.text(0.02, y, suite_txt, fontsize=10, verticalalignment='top', family='monospace')
        y -= 0.11

    y -= 0.05
    ax_text.text(0, y, "LATENCY (Fast / Thinking)", fontsize=14, fontweight='bold', color='#9b59b6')
    y -= 0.04
    
    intent_map = {1: 'Theory', 2: 'Coding', 3: 'CLI'}
    for idx, name in intent_map.items():
        try:
            f_l = latency_stats.loc['fast', idx]
            t_l = latency_stats.loc['thinking', idx]
            ax_text.text(0.02, y, f"➤ {name}: {f_l:.1f}s / {t_l:.1f}s", fontsize=11, family='monospace')
            y -= 0.05
        except: pass

    # --- CENTER & RIGHT: Heatmaps ---
    suites = sorted(df['suite'].unique())
    max_tests = df['test_idx'].max()
    
    fast_mtx = np.zeros((max_tests, len(suites)))
    think_mtx = np.zeros((max_tests, len(suites)))

    for i, suite in enumerate(suites):
        suite_data = df[df['suite'] == suite]
        for _, row in suite_data.iterrows():
            idx = row['test_idx'] - 1
            f_ok = str(row['format_ok']).lower() == 'true'
            e_exists = pd.notna(row['exec_ok'])
            e_ok = str(row['exec_ok']).lower() == 'true' if e_exists else None
            has_warn = str(row['warning']).lower() == 'true'
            
            if row['processing_type'] == 'fast':
                if e_exists:
                    if e_ok and f_ok: fast_mtx[idx, i] = 1 # Green
                    elif e_ok and not f_ok: fast_mtx[idx, i] = 3 # Orange
                    else: fast_mtx[idx, i] = 2 # Red
                else:
                    fast_mtx[idx, i] = 1 if f_ok else 2
            else: # thinking mode
                if e_exists:
                    if e_ok and f_ok: think_mtx[idx, i] = 1 # Green
                    elif has_warn: think_mtx[idx, i] = 2 # Yellow
                    elif e_ok and not f_ok: think_mtx[idx, i] = 4 # Orange
                    else: think_mtx[idx, i] = 3 # Red
                else:
                    if f_ok: think_mtx[idx, i] = 1 # Green
                    elif has_warn: think_mtx[idx, i] = 2 # Yellow
                    else: think_mtx[idx, i] = 3 # Red

    # Fast Table
    cmap_f = plt.matplotlib.colors.ListedColormap(['#1e1e1e', '#2ecc71', '#e74c3c', '#e67e22'])
    ax_fast.imshow(fast_mtx, cmap=cmap_f, aspect='auto')
    ax_fast.set_title("FAST MODE", fontsize=14, color='#2ecc71')

    # Thinking Table
    cmap_t = plt.matplotlib.colors.ListedColormap(['#1e1e1e', '#2ecc71', '#f1c40f', '#e74c3c', '#e67e22'])
    ax_think.imshow(think_mtx, cmap=cmap_t, aspect='auto')
    ax_think.set_title("THINKING MODE", fontsize=14, color='#f1c40f')

    for ax in [ax_fast, ax_think]:
        ax.set_xticks(np.arange(len(suites)))
        ax.set_xticklabels([s.split(' ')[0] for s in suites], fontsize=9)
        ax.set_yticks(np.arange(max_tests))
        ax.set_yticklabels(np.arange(1, max_tests + 1), fontsize=8)
        ax.set_xticks(np.arange(-.5, len(suites), 1), minor=True)
        ax.set_yticks(np.arange(-.5, max_tests, 1), minor=True)
        ax.grid(which='minor', color='#333333', linestyle='-', linewidth=0.5)

    # Legend
    f_patches = [
        mpatches.Patch(color='#2ecc71', label='Pass'), 
        mpatches.Patch(color='#e74c3c', label='Fail'),
        mpatches.Patch(color='#e67e22', label='Logic OK')
    ]
    t_patches = [
        mpatches.Patch(color='#2ecc71', label='Pass'), 
        mpatches.Patch(color='#f1c40f', label='Fail+Warn'), 
        mpatches.Patch(color='#e74c3c', label='Fail+NoWarn'),
        mpatches.Patch(color='#e67e22', label='Logic OK')
    ]
    ax_fast.legend(handles=f_patches, loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=2, fontsize=8)
    ax_think.legend(handles=t_patches, loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3, fontsize=8)

    # --- BOTTOM: Global Summary ---
    ax_summary.axis('off')
    f_tot = sum(s['fast_total'] for s in stats.values())
    f_pass = sum(s['fast_pass'] for s in stats.values())
    t_tot = sum(s['think_total'] for s in stats.values())
    t_pass = sum(s['think_pass'] for s in stats.values())
    
    f_rate = (f_pass/f_tot*100) if f_tot > 0 else 0
    t_rate = (t_pass/t_tot*100) if t_tot > 0 else 0
    
    summary = f"FAST: {f_pass}/{f_tot} ({f_rate:.1f}%) | THINKING: {t_pass}/{t_tot} ({t_rate:.1f}%)"
    ax_summary.text(0.5, 0.5, summary, fontsize=20, fontweight='bold', ha='center', va='center',
                    bbox=dict(facecolor='#000', edgecolor='#3498db', boxstyle='round,pad=0.5'))

    plt.tight_layout()
    plt.savefig('results/dashboard_v2.png', dpi=150)
    plt.show()

if __name__ == "__main__":
    create_dashboard()