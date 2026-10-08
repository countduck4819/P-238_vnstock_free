# Wave v6: two-stage H20 trend model

V6 keeps the existing two-stage XGBoost architecture but makes the first-stage
target operationally shorter: the H20 wave-entry label. The first classifier
emits `p_trend`; implementation keeps the compatibility name `p_entry`. The
second model predicts `y_strength` only for H20-positive rows. No H150 labels,
final-test rows, or feature-selection results are used to choose the v6 target.

The experiment intentionally uses all 81 v1 features: the 76-feature v5 set
was not proven to improve stable ranking, so combining both changes would make
the binary-target comparison ambiguous.
