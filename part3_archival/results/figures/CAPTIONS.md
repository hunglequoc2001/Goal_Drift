# Figure captions (Exp02)

## fig1_bcm_by_representation
SWE-bench Pro public archive, primary cohort (5 models, SWE-agent 1.1, 250-turn config, 715 matched tasks, one attempt per model-task). Same trajectories, four representations. Predictor: released BCM LightGBM, task-grouped 5-fold CV (seed 0); tree-path TreeSHAP. Points: BCM; bars: 95% paired task-cluster bootstrap (2,000 resamples, attributions held fixed). GPT-5 is ranked first under the authors' loader (R0) and last under role-aware parsing (R2): 58% of its R0 parses are empty because GPT-5's thought text is hidden.

## fig2_label_permutation_controls
Real-label BCM (dot) vs. 50 pre-specified label permutations (seeds 1000-1049): within model (square, preserves each model's success rate) and global (triangle). Predictor: released BCM LightGBM, task-grouped 5-fold CV; tree-path TreeSHAP. Under role-aware parsing in the primary cohort every model's real BCM lies inside its within-model null band: the BCM level is reproduced without any trajectory-outcome link inside a model.

## fig3_rank_by_configuration
Model rank (1 = highest BCM) and BCM (mean over 10 task-grouped CV seeds; 3 for LGBM-tuned) for every representation x predictor configuration, primary cohort. 'raw' = train-fold z-scored features without a predictor. No model keeps its rank across configurations.

## fig4_cross_model_same_task_similarity
Mean cosine between attribution vectors of two models' trajectories on the same task (left, off-diagonal) or on different tasks (right); diagonal of the left panel = the model's own global BCM (all cross-task pairs). Primary cohort, R2, released LightGBM, task-grouped CV seed 0. Descriptive only: one attempt per model-task, so this does not measure within-model repeatability. Two different models on the same task are more similar than one model across tasks.

## fig5_bcm_vs_within_model_auc
Each point = one model x representation x predictor (LGBM, logistic) x label scheme (real; null medians over 50 permutations), all cohorts, task-grouped CV. BCM does not track the predictor's within-model discriminative ability; null models with chance-level within-model AUC reach the same BCM range.

## fig6_bcm_depends_on_companion_systems
Companion sensitivity. For every subset of systems containing the target, the released BCM LightGBM is fit on that subset only (task-grouped 5-fold CV, seed 0, R2 role-aware features, tree-path TreeSHAP); the target's trajectories and labels are identical in every fit. Points: median over subsets of that size; bars: min-max. Fit on a system alone (k = 1), every BCM is 0.001-0.019 although the predictor is informative (within-system AUC 0.61-0.77); BCM grows with the number of other systems in the pool.
