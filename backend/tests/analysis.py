import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import numpy as np
import glob
import os
import re

# Style
plt.style.use('dark_background')
SAVE_BASE_PATH = "results/analysis"
CATEGORY_ORDER = ["Fast", "Planning", "Chain_of_draft", "Reflection_refine"]

def get_next_analysis_path():
    if not os.path.exists(SAVE_BASE_PATH):
        os.makedirs(SAVE_BASE_PATH)
    
    existing_dirs = [d for d in os.listdir(SAVE_BASE_PATH) if os.path.isdir(os.path.join(SAVE_BASE_PATH, d))]
    indices = [int(re.findall(r'\d+', d)[0]) for d in existing_dirs if re.findall(r'\d+', d)]
    
    next_idx = max(indices) + 1 if indices else 0
    path = os.path.join(SAVE_BASE_PATH, f"v{next_idx}")
    os.makedirs(path)
    return path

# --- Agregation ---

def parse_results(path, process_fast=True, process_think=True):
    csv_files = glob.glob(path)
    if not csv_files: return None, None, None
    all_data = []
    for file in csv_files:
        df = pd.read_csv(file)
        df['exec_ok'] = pd.to_numeric(df['exec_ok'], errors='coerce')
        df['test_idx'] = df['id'].apply(lambda x: int(re.findall(r'\d+', x)[-1]))
        df['suite'] = os.path.basename(file).replace('.csv', '').replace('_', ' ').title()
        df['success_count'] = df.apply(
            lambda r: r['format_ok'] if pd.isna(r['exec_ok']) else min(r['format_ok'], r['exec_ok']), axis=1
        )
        all_data.append(df)
    full_df = pd.concat(all_data)
    return full_df

def apply_old_data():
    fast_path = "results/original_1_5B_q4/*.csv"
    thinking_paths = [
        "results/original_1_5B_q4/1_planning_logic/*.csv",
        "results/original_1_5B_q4/2_chain_of_draft/*.csv",
        "results/original_1_5B_q4/3_reflection_refine/*.csv"
    ]
    thinking_names = ["Planning", "Chain_of_draft", "Reflection_refine"]
    
    df_fast = parse_results(fast_path)
    df_fast = df_fast[df_fast['processing_type'] == 'fast']
    df_fast['processing_type'] = "Fast"
    
    dfs = [df_fast]
    for path, name in zip(thinking_paths, thinking_names):
        df_t = parse_results(path)
        df_t = df_t[df_t['processing_type'] == 'thinking']
        df_t['processing_type'] = name
        dfs.append(df_t)
    
    full_df = pd.concat(dfs, ignore_index=True)
    categories = ["Fast"] + thinking_names
    return full_df, categories

# --- Analysis ---

def export_text_stats(df, categories, path):
    with open(os.path.join(path, "0_text_stats.txt"), "w", encoding="utf-8") as f:
        f.write("=== AGGREGATED STATISTICS ===\n\n")
        for cat in categories:
            m_df = df[df['processing_type'] == cat]
            total_tests = len(m_df)
            if total_tests == 0: continue
            
            pass_100 = (m_df['success_count'] == m_df['repeats']).sum()
            pass_partial = (m_df['success_count'] > 0).sum()
            
            total_attempts = m_df['repeats'].sum()
            total_successes = m_df['success_count'].sum()
            total_fails = total_attempts - total_successes
            
            success_rate = (total_successes / total_attempts) * 100
            total_warns = m_df['warning'].sum()
            total_wrong_warns = m_df['wrong_warnings'].sum()
            
            warn_efficiency = (total_warns / total_fails * 100) if total_fails > 0 else 0
            interference = (total_wrong_warns / total_successes * 100) if total_successes > 0 else 0
            
            f.write(f"MODE: {cat}\n")
            f.write(f"  - Tests: {pass_100} (100%) / {pass_partial} (Partial) / {total_tests} (Total)\n")
            f.write(f"  - Success Rate: {success_rate:.1f}% (Total attempts: {total_attempts})\n")
            f.write(f"  - Warnings: {int(total_warns)} total | Wrong Warnings: {int(total_wrong_warns)}\n")
            f.write(f"  - Warning Efficiency (detected errors): {warn_efficiency:.1f}%\n")
            f.write(f"  - Interference (wrongly flagged success): {interference:.1f}%\n")
            f.write("-" * 40 + "\n")

def plot_1_general_heatmap(df, categories, path):
    suites = sorted(df['suite'].unique())
    max_tests = df['test_idx'].max()
    fig, axes = plt.subplots(1, len(categories), figsize=(4*len(categories), 10), sharey=True)
    if len(categories) == 1: axes = [axes]

    colors = ['#1e1e1e', '#1b5e20', "#36a162", "#30cb1e", '#f1c40f', '#e74c3c', '#e67e22']
    cmap = plt.matplotlib.colors.ListedColormap(colors)

    for i, cat in enumerate(categories):
        matrix = np.zeros((max_tests, len(suites)))
        c_df = df[df['processing_type'] == cat]
        for _, row in c_df.iterrows():
            val = 5 # Fail
            if row['success_count'] == row['repeats']: val = 1
            elif row['success_count'] > row['repeats']/2: val = 2
            elif row['wrong_warnings'] > 0: val = 6
            elif row['success_count'] > 0: val = 3
            elif row['warning'] > 0: val = 4
            matrix[row['test_idx']-1, suites.index(row['suite'])] = val
        
        ax = axes[i]
        ax.imshow(matrix, cmap=cmap, aspect='auto', vmin=0, vmax=6)
        ax.set_title(cat.upper(), color='white', fontweight='bold', pad=15)
        ax.set_xticks(np.arange(len(suites)))
        ax.set_xticklabels([s.split(' ')[0] for s in suites], rotation=45, fontsize=8)
        
        ax.set_yticks(np.arange(max_tests))
        ax.set_yticklabels(np.arange(1, max_tests + 1), fontsize=7)
        ax.grid(which='both', color='#333333', linestyle='-', linewidth=0.5)

    patches = [
        mpatches.Patch(color='#1b5e20', label='100% Pass'),
        mpatches.Patch(color='#36a162', label='>50% Pass'),
        mpatches.Patch(color='#30cb1e', label='Partial Pass'),
        mpatches.Patch(color='#e74c3c', label='Fail'),
        mpatches.Patch(color='#f1c40f', label='Fail + Warning'),
        mpatches.Patch(color='#e67e22', label='Wrong Warning')
    ]
    fig.legend(handles=patches, loc='lower center', bbox_to_anchor=(0.5, 0.02), ncol=3)
    plt.tight_layout(rect=[0, 0.08, 1, 1])
    plt.savefig(os.path.join(path, "1_general_heatmap.png"), dpi=150)

def plot_2_percentage_heatmap(df, categories, path):
    suites = sorted(df['suite'].unique())
    max_tests = df['test_idx'].max()
    fig, axes = plt.subplots(1, len(categories), figsize=(4*len(categories), 10), sharey=True)
    if len(categories) == 1: axes = [axes]

    for i, cat in enumerate(categories):
        matrix = np.full((max_tests, len(suites)), np.nan)
        c_df = df[df['processing_type'] == cat]
        for _, row in c_df.iterrows():
            matrix[row['test_idx']-1, suites.index(row['suite'])] = row['success_count'] / row['repeats']
        
        sns.heatmap(matrix, ax=axes[i], cmap="RdYlGn", cbar=(i == len(categories)-1), 
                    vmin=0, vmax=1, mask=np.isnan(matrix), linewidths=0.5, linecolor='#222')
        axes[i].set_facecolor('black')
        axes[i].set_title(f"{cat} Success %")
        axes[i].set_xticklabels([s.split(' ')[0] for s in suites], rotation=45)
        axes[i].set_yticks(np.arange(max_tests) + 0.5)
        axes[i].set_yticklabels(np.arange(1, max_tests + 1), rotation=0)

    plt.tight_layout()
    plt.savefig(os.path.join(path, "2_percentage_heatmap.png"), dpi=150)

def plot_3_4_bar_charts(df, categories, path, group_by='suite', filename="3_bars_by_suite.png"):
    plt.figure(figsize=(12, 6))
    
    agg = df.groupby([group_by, 'processing_type']).apply(
        lambda x: x['success_count'].sum() / x['repeats'].sum()
    ).reset_index(name='ratio')
    
    sns.barplot(data=agg, x=group_by, y='ratio', hue='processing_type', 
                hue_order=[c for c in CATEGORY_ORDER if c in categories], palette='viridis')
    
    plt.title(f"Success Ratio by {group_by}")
    plt.xticks(rotation=30)
    plt.ylim(0, 1.1)
    plt.ylabel("Success Rate (0.0 - 1.0)")
    plt.grid(axis='y', alpha=0.2)
    plt.legend(title="Mode")
    plt.tight_layout()
    plt.savefig(os.path.join(path, filename))

def plot_5_6_7_latency_boxes(df, path):
    # 5. Latency by Mode
    plt.figure(figsize=(10, 6))
    sns.boxplot(data=df, x='processing_type', y='time_s', palette='magma')
    plt.title("Latency Distribution by Mode")
    plt.savefig(os.path.join(path, "5_latency_by_mode.png"))

    # 6. Latency by Suite
    plt.figure(figsize=(12, 8))
    sns.boxplot(data=df, x='suite', y='time_s', hue='processing_type')
    plt.title("Latency by Test Block")
    plt.xticks(rotation=20)
    plt.savefig(os.path.join(path, "6_latency_by_suite.png"))

    # 7. Latency by Intent
    plt.figure(figsize=(12, 6))
    intent_map = {1: 'Theory', 2: 'Coding', 3: 'CLI'}
    df['intent_name'] = df['intent'].map(intent_map)
    sns.boxplot(data=df, x='intent_name', y='time_s', hue='processing_type')
    plt.title("Latency by Intent Type")
    plt.savefig(os.path.join(path, "7_latency_by_intent.png"))

# --- Warnings (8-11) ---

def plot_8_9_warning_confusion_matrices(df, categories, path, coding_only=False):
    """
    Visualizes Warning Confusion Matrices:
    TP: Wrong + Warning | TN: Right + No Warning
    FP: Right + Warning | FN: Wrong + No Warning
    """
    plot_df = df[df['intent'] == 2].copy() if coding_only else df.copy()
    suffix = "coding" if coding_only else "all"
    
    fig, axes = plt.subplots(1, len(categories), figsize=(4*len(categories), 4))
    if len(categories) == 1: axes = [axes]
    
    for i, cat in enumerate(categories):
        c_df = plot_df[plot_df['processing_type'] == cat]
        if c_df.empty: continue
        
        # Calculate attempt-level stats
        # Total attempts = repeats. We assume success_count are the 'Rights'
        rights = c_df['success_count'].sum()
        wrongs = (c_df['repeats'] - c_df['success_count']).sum()
        
        fp = c_df['wrong_warnings'].sum() # Warning on Right
        tn = rights - fp                  # No Warning on Right
        tp = c_df['warning'].sum() - fp   # Warning on Wrong
        fn = wrongs - tp                  # No Warning on Wrong
        
        matrix = np.array([[tp, fp], [fn, tn]])
        labels = [f"Warning\n({tp+fp})", f"No Warn\n({fn+tn})"]
        cols = [f"Wrong\n({wrongs})", f"Right\n({rights})"]
        
        sns.heatmap(matrix, annot=True, fmt='.0f', ax=axes[i], cmap="Purples",
                    xticklabels=cols, yticklabels=labels, cbar=False)
        axes[i].set_title(f"{cat} ({suffix})")

    plt.tight_layout()
    plt.savefig(os.path.join(path, f"{'9' if coding_only else '8'}_conf_matrix_{suffix}.png"), dpi=150)

def plot_10_warning_proportions(df, categories, path):
    """
    Bar chart by suites: 
    Up (Blue-Green): Proportion of Correct Warnings (True Positives)
    Down (Orange-Red): Proportion of False Warnings (False Positives)
    """
    suites = sorted(df['suite'].unique())
    # Exclude Fast mode as it usually has 0 warnings by design
    think_cats = [c for c in categories if c != "Fast"]
    if not think_cats: return

    fig, ax = plt.subplots(figsize=(14, 7))
    
    x = np.arange(len(suites))
    width = 0.8 / len(think_cats)
    
    # Colors for the 3 thinking modes
    up_colors = ['#1abc9c', '#16a085', '#27ae60']
    down_colors = ['#e67e22', '#d35400', '#c0392b']

    for i, cat in enumerate(think_cats):
        c_df = df[df['processing_type'] == cat]
        correct_rates = []
        false_rates = []
        
        for s in suites:
            s_df = c_df[c_df['suite'] == s]
            if s_df.empty:
                correct_rates.append(0); false_rates.append(0)
                continue
            
            total_attempts = s_df['repeats'].sum()
            # Correct Warning = Total Warnings - Wrong Warnings
            correct_warns = s_df['warning'].sum() - s_df['wrong_warnings'].sum()
            false_warns = s_df['wrong_warnings'].sum()
            
            correct_rates.append(correct_warns / total_attempts)
            false_rates.append(-false_warns / total_attempts) # Negative for downward plot

        offset = i * width - (len(think_cats)*width)/2 + width/2
        ax.bar(x + offset, correct_rates, width, label=f"{cat} (Correct)", color=up_colors[i % 3])
        ax.bar(x + offset, false_rates, width, label=f"{cat} (False)", color=down_colors[i % 3], alpha=0.8)

    ax.axhline(0, color='white', linewidth=1)
    ax.set_title("Warning Validity Proportions (Up: Correct / Down: False)", fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels([s.split(' ')[0] for s in suites], rotation=30)
    ax.legend(loc='upper right', fontsize='small', ncol=2)
    plt.tight_layout()
    plt.savefig(os.path.join(path, "10_warning_proportions.png"), dpi=150)

def plot_11_response_effectiveness(df, categories, path):
    """
    Effectiveness = (Wrong AND Warning) OR (Right AND NO Warning).
    Compares Fast mode vs thinking modes.
    """
    suites = sorted(df['suite'].unique())
    plt.figure(figsize=(14, 6))
    
    # Calculate Effective Rate: 
    # Effective attempts = (Right - WrongWarnings) + (TotalWarnings - WrongWarnings)
    # This simplifies to: TotalAttempts - Fn (Wrong but No Warn) - Fp (Right but Warn)
    def calc_effective_rate(group):
        total = group['repeats'].sum()
        fp = group['wrong_warnings'].sum()
        # total_wrongs = total - success_count
        # tp = warning - fp
        # fn = total_wrongs - tp
        fn = (group['repeats'] - group['success_count']).sum() - (group['warning'].sum() - fp)
        effective_count = total - fp - fn
        return effective_count / total

    agg = df.groupby(['suite', 'processing_type']).apply(calc_effective_rate).reset_index(name='eff_rate')
    
    sns.barplot(data=agg, x='suite', y='eff_rate', hue='processing_type', 
                hue_order=categories, palette='husl')
    
    plt.title("Model 'Honesty' Effectiveness per Suite", fontsize=14)
    plt.ylabel("Effectiveness Rate (Correct or Self-Aware)")
    plt.axhline(0.5, color='red', linestyle='--', alpha=0.5)
    plt.xticks(rotation=30)
    plt.legend(title="Mode", loc='lower right')
    plt.tight_layout()
    plt.savefig(os.path.join(path, "11_response_effectiveness.png"), dpi=150)


def main():
    print("🚀 Starting analysis...")
    df, categories = apply_old_data()
    analysis_dir = get_next_analysis_path()
    print(f"📂 Saving results to: {analysis_dir}")

    # 0. Text Stats
    export_text_stats(df, categories, analysis_dir)
    
    # 1. General Heatmap
    plot_1_general_heatmap(df, categories, analysis_dir)
    
    # 2. Percentage Heatmap
    plot_2_percentage_heatmap(df, categories, analysis_dir)
    
    # 3. Bars by Suite
    plot_3_4_bar_charts(df, categories, analysis_dir, group_by='suite', filename="3_bars_by_suite.png")
    
    # 4. Bars by Intent
    intent_map = {1: 'Theory', 2: 'Coding', 3: 'CLI'}
    df['intent_name'] = df['intent'].map(intent_map)
    plot_3_4_bar_charts(df, categories, analysis_dir, group_by='intent_name', filename="4_bars_by_intent.png")
    
    # 5, 6, 7. Latency Analysis
    plot_5_6_7_latency_boxes(df, analysis_dir)

    print("🔍 Generating warning & effectiveness analysis (8-11)...")
    # 8. Confusion Matrix (All)
    plot_8_9_warning_confusion_matrices(df, categories, analysis_dir, coding_only=False)
    # 9. Confusion Matrix (Coding)
    plot_8_9_warning_confusion_matrices(df, categories, analysis_dir, coding_only=True)
    # 10. Proportions Up/Down
    plot_10_warning_proportions(df, categories, analysis_dir)
    # 11. Effectiveness
    plot_11_response_effectiveness(df, categories, analysis_dir)

    print("✅ Analysis complete.")

if __name__ == "__main__":
    main()