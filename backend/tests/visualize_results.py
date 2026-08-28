import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import glob
import os
import re

INDEX = "7"
CVV_PATH = "results/original_1_5B_q4/*.csv"
SAVE_PATH = f"results/dashboards/dashboard_v{INDEX}.png"

def parse_results(path = CVV_PATH, process_fast = True, process_think = True):
    csv_files = glob.glob(path)
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
        
        # Set which modes process
        mode_list = []
        if process_fast:
            mode_list.append('fast')
        if process_think:
            mode_list.append('thinking')
        # Suite Performance Stats
        for mode in mode_list:
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
                'display': f"{pass_100}/{pass_partial+pass_100}/{total_tests}",
                'warn_info': f"Warn on Fail: {warn_rate:.1f}% | Wrong Warn: {wrong_warn_rate:.1f}%"
            }

    full_df = pd.concat(all_data)
    
    # Latency: sum(time_s) / sum(repeats)
    latency = full_df.groupby(['processing_type', 'intent']).apply(
        lambda x: x['time_s'].sum() / x['repeats'].sum()
    ).unstack()
    
    return full_df, suite_stats, latency

def create_dashboard(df, stats, latency_stats, categories = ["Fast", "Thinking"], save_path = SAVE_PATH):
    plt.style.use('dark_background')
    
    fig_width = 5 + (6 * len(categories))
    fig = plt.figure(figsize=(fig_width, 12))
    
    text_col_weight = 1.0 if len(categories) > 2 else 0.8
    gs_main = fig.add_gridspec(2, 2, width_ratios=[1.2, len(categories)], height_ratios=[1, 0.3])
    gs_tables = gs_main[0, 1].subgridspec(1, len(categories), wspace=0.08)

    ax_text = fig.add_subplot(gs_main[0, 0]) 
    ax_list = [fig.add_subplot(gs_tables[0, i]) for i in range(len(categories))]
    ax_summary = fig.add_subplot(gs_main[1, :])

    # --- LEFT: Text Stats ---
    ax_text.axis('off')
    y = 0.98
    ax_text.text(0, y, "SUITE PERFORMANCE (100% / Partial / Total)", fontsize=14, fontweight='bold', color='#3498db')
    y -= 0.05
    
    suites = sorted(df['suite'].unique())
    y_step = 0.05 + (0.025 * len(categories))
    
    for s_name in suites:
        txt = f"● {s_name}\n"
        for category in categories:
            c_s = stats.get(f"{s_name}_{category.lower()}", {'display': 'N/A', 'warn_info': ''})
            txt += f"  {category}: {c_s['display']} ({c_s['warn_info']})\n"
        ax_text.text(0.02, y, txt, fontsize=9, verticalalignment='top', family='monospace')
        y -= y_step

    y -= 0.02
    ax_text.text(0, y, "AVG LATENCY (seconds per attempt)", fontsize=13, fontweight='bold', color='#9b59b6')
    y -= 0.04
    intent_map = {1: 'Theory', 2: 'Coding', 3: 'CLI'}
    for idx, name in intent_map.items():
        txt = f"➤ {name}: "
        for category in categories:
            try:
                c_l = latency_stats.loc[category.lower(), idx]
                txt += f"{c_l:.2f}s ({category}) | "
            except: pass
        ax_text.text(0.02, y, txt, fontsize=10, family='monospace')
        y -= 0.04

    # --- CENTER & RIGHT: Heatmaps ---
    max_tests = df['test_idx'].max()
    catg_matx = [np.zeros((max_tests, len(suites))) for _ in categories]
    cat_to_idx = {cat.lower(): i for i, cat in enumerate(categories)}

    for i, suite in enumerate(suites):
        suite_data = df[df['suite'] == suite]
        for _, row in suite_data.iterrows():
            idx = row['test_idx'] - 1
            reps = row['repeats']
            success = row['success_count']
            
            if success == reps: val = 1
            elif success > reps / 2: val = 2
            elif success > 0: val = 3
            elif row['wrong_warnings']>0: val = 6
            elif row['warning'] > 0: val = 4
            else: val = 5
            
            target_cat_idx = cat_to_idx.get(row['processing_type'].lower())
            if target_cat_idx is not None:
                catg_matx[target_cat_idx][idx, i] = val

    colors = ['#1e1e1e', '#1b5e20', "#36a162", "#30cb1e", '#f1c40f', '#e74c3c', '#e67e22']
    cmap = plt.matplotlib.colors.ListedColormap(colors)
    
    title_colors = ['#2ecc71', '#f1c40f', '#3498db', '#9b59b6', '#e67e22']
    for i, (ax, mtx, cat_name) in enumerate(zip(ax_list, catg_matx, categories)):
        clr = title_colors[i % len(title_colors)]
        ax.imshow(mtx, cmap=cmap, aspect='auto', vmin=0, vmax=6)
        ax.set_title(f"{cat_name.upper()}", fontsize=14, color=clr, fontweight='bold')
        ax.set_xticks(np.arange(len(suites)))
        ax.set_xticklabels([s.split(' ')[0] for s in suites], fontsize=9)
        ax.set_yticks(np.arange(max_tests))
        ax.set_yticklabels(np.arange(1, max_tests + 1), fontsize=8)
        ax.grid(which='both', color='#333333', linestyle='-', linewidth=0.5)

    # Legends
    patches = [
        mpatches.Patch(color='#1b5e20', label='100% Pass'),
        mpatches.Patch(color='#36a162', label='>50% Pass'),
        mpatches.Patch(color='#30cb1e', label='Part. Pass'),
        mpatches.Patch(color='#e74c3c', label='Fail'),
        mpatches.Patch(color='#f1c40f', label='Fail+Warn'),
        mpatches.Patch(color='#e67e22', label='Wrong Warn')
        
    ]
    fig.legend(handles=patches, loc='lower center', bbox_to_anchor=(0.5, 0.18), ncol=6, fontsize=10)

    # --- BOTTOM: Global Summary ---
    ax_summary.axis('off')
    
    def get_summary(mode_name):
        m_df = df[df['processing_type'].str.lower() == mode_name.lower()]
        if m_df.empty: return "0 / 0 / 0"
        t_100 = (m_df['success_count'] == m_df['repeats']).sum()
        t_part = ((m_df['success_count'] > 0) & (m_df['success_count'] < m_df['repeats'])).sum()
        return f"{t_100} / {t_part+t_100} / {len(m_df)}"

    summary_parts = [f"{cat.upper()}: {get_summary(cat)}" for cat in categories]
    summary_text = "GLOBAL (100% / Partial / Total)\n" + "   |   ".join(summary_parts)
    
    ax_summary.text(0.5, 0.2, summary_text, fontsize=18, fontweight='bold', ha='center', 
                    family='monospace', bbox=dict(facecolor='#000', edgecolor='#3498db', boxstyle='round,pad=1'))

    plt.tight_layout(rect=[0, 0.05, 1, 0.95]) 
    plt.savefig(f'{save_path}', dpi=150)
    print(f"Dashboard saved to {save_path}")

def create_default_dashboard():
        df, stats, latency_stats = parse_results()
        create_dashboard(df, stats, latency_stats)

def recalculate_stats(full_df, categories):
    suite_stats = {}
    suites = full_df['suite'].unique()
    for suite in suites:
        s_df = full_df[full_df['suite'] == suite]
        for cat in categories:
            m_df = s_df[s_df['processing_type'].str.lower() == cat.lower()]
            
            if m_df.empty: continue
            reps = m_df['repeats'].max() 
            
            total_tests = len(m_df)
            pass_100 = (m_df['success_count'] == reps).sum()
            pass_partial = ((m_df['success_count'] > 0) & (m_df['success_count'] < reps)).sum()
            
            total_attempts = m_df['repeats'].sum()
            total_success_attempts = m_df['success_count'].sum()
            total_failed_attempts = total_attempts - total_success_attempts
            
            warn_rate = (m_df['warning'].sum() / total_failed_attempts * 100) if total_failed_attempts > 0 else 0
            total_success = m_df['success_count'].sum()
            wrong_warn_rate = (m_df['wrong_warnings'].sum() / total_success * 100) if total_success > 0 else 0
            
            key = f"{suite}_{cat.lower()}"
            suite_stats[key] = {
                'display': f"{pass_100}/{pass_partial+pass_100}/{total_tests}",
                'warn_info': f"W: {warn_rate:.0f}% | WW: {wrong_warn_rate:.0f}%"
            }
    # Latency calculation
    latency_stats = full_df.groupby(['processing_type', 'intent']).apply(
        lambda x: x['time_s'].sum() / x['repeats'].sum()
    ).unstack() 
    latency_stats.index = latency_stats.index.str.lower()
    return suite_stats, latency_stats

def apply_data_2_models(path1, path2, names):
    # Load first model 
    df1, _, _ = parse_results(path1, process_fast=True, process_think=False)
    df1['processing_type'] = names[0]
    
    # Load second model
    df2, _, _ = parse_results(path2, process_fast=True, process_think=False)
    df2['processing_type'] = names[1]
    
    full_df = pd.concat([df1, df2], ignore_index=True)
    stats, latency = recalculate_stats(full_df, names)
    return full_df, stats, latency

def create_2_models_dashboard():
    orig_path = "results/original_1_5B_q4/*.csv"
    alter_path = "results/alternative_3B_q2/*.csv"
    names = ["1.5B_q4", "3B_q2"]
    df, stats, latency_stats = apply_data_2_models(orig_path, alter_path, names)
    # Fixed save_path logic
    create_dashboard(df, stats, latency_stats, categories=names, save_path=SAVE_PATH.replace(".png", "_two_models.png"))

def apply_data_thinking_mods(fast_path, thinking_paths, thinking_names):
    # Load base Fast mode
    df_fast, _, _ = parse_results(fast_path, process_fast=True, process_think=False)
    df_fast['processing_type'] = "Fast"
    
    dfs = [df_fast]
    # Load each thinking strategy
    for path, name in zip(thinking_paths, thinking_names):
        df_t, _, _ = parse_results(path, process_fast=False, process_think=True)
        df_t['processing_type'] = name
        dfs.append(df_t)
    
    full_df = pd.concat(dfs, ignore_index=True)
    all_names = ["Fast"] + thinking_names
    stats, latency = recalculate_stats(full_df, all_names)
    return full_df, stats, latency

def create_3_thinking_mods_dashboard(): # Fixed typo in function name
    fast_path = "results/original_1_5B_q4/*.csv"
    thinking_paths = [
        "results/original_1_5B_q4/1_planning_logic/*.csv",
        "results/original_1_5B_q4/2_chain_of_draft/*.csv",
        "results/original_1_5B_q4/3_reflection_refine/*.csv"
    ]
    thinking_names = ["Planning", "Chain_of_draft", "Reflection_refine"]
    
    df, stats, latency_stats = apply_data_thinking_mods(fast_path, thinking_paths, thinking_names)
    
    # Fixed: use extend or list addition instead of append to keep list flat
    names = ["Fast"] + thinking_names
    
    create_dashboard(df, stats, latency_stats, categories=names, save_path=SAVE_PATH.replace(".png", "_thinking_logic.png"))


if __name__ == "__main__":
    # create_2_models_dashboard()
    create_3_thinking_mods_dashboard()