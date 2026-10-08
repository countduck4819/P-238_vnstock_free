<#
.SYNOPSIS
Run the locked H120 ranker Phase-C workflow against a locally restored dataset.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$DatasetRun,

    [string]$BaselineOof = "models/wave_ignition_snapshot/xgboost_continuation_h120/runs/20260823T052814Z/predictions/oof_predictions.parquet",

    [string]$OutputRoot = "models/wave_ignition/h120_ranker_generation_v2",

    [ValidateRange(1, 100)]
    [int]$R3Trials = 20
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$protocol = Join-Path $projectRoot "configs\experiments\h120_ranker_generation_v2.yaml"
$modelConfig = Join-Path $projectRoot "configs\experiments\h120_ranker_stock_primitives_v1.yaml"
$folds = "fold_2020,fold_2021,fold_2022,fold_2023"
function Resolve-ProjectPath([string]$PathValue) {
    if ([IO.Path]::IsPathRooted($PathValue)) {
        return [IO.Path]::GetFullPath($PathValue)
    }
    return [IO.Path]::GetFullPath((Join-Path $projectRoot $PathValue))
}

$datasetPath = Resolve-ProjectPath $DatasetRun
$baselinePath = Resolve-ProjectPath $BaselineOof
$outputPath = Resolve-ProjectPath $OutputRoot
$experimentPath = Join-Path $projectRoot "experiments\h120_improvement\E08_generation_v2"

if (-not (Test-Path (Join-Path $datasetPath "dataset"))) {
    throw "DatasetRun must contain a dataset directory: $datasetPath"
}
if (-not (Test-Path $baselinePath)) {
    throw "Baseline OOF is missing: $baselinePath"
}
if (-not (Test-Path $python)) {
    throw "Project Python environment is missing: $python"
}

function Get-NewestRun([string]$Root) {
    $runs = Get-ChildItem -LiteralPath (Join-Path $Root "runs") -Directory |
        Sort-Object LastWriteTimeUtc -Descending
    if (-not $runs) {
        throw "No model run was created under $Root"
    }
    return $runs[0].FullName
}

function Invoke-RankerRun([int]$Seed, [string]$Name) {
    $modelRoot = Join-Path $outputPath $Name
    $null = & $python (Join-Path $projectRoot "scripts\train_h120_ranker.py") `
        --dataset-run $datasetPath `
        --config $modelConfig `
        --output-root $modelRoot `
        --folds $folds `
        --protocol $protocol `
        --random-seed $Seed
    if ($LASTEXITCODE -ne 0) { throw "Ranker training failed for seed $Seed" }

    $runPath = Get-NewestRun $modelRoot
    $evaluationPath = Join-Path $experimentPath ("R2\seed_{0}" -f $Seed)
    if ($Seed -eq 238) { $evaluationPath = Join-Path $experimentPath "R1" }
    $null = & $python (Join-Path $projectRoot "scripts\evaluate_h120_ranker.py") `
        --ranker-oof (Join-Path $runPath "predictions\oof_ranker_predictions.parquet") `
        --baseline-oof $baselinePath `
        --model-seed $Seed `
        --output $evaluationPath
    if ($LASTEXITCODE -ne 0) { throw "Ranker evaluation failed for seed $Seed" }
    return $evaluationPath
}

Push-Location $projectRoot
try {
    $r1Path = Invoke-RankerRun -Seed 238 -Name "R1_seed_238"
    $seedMetricPaths = @()
    foreach ($seed in 238, 239, 240, 241, 242) {
        $evaluationPath = Invoke-RankerRun -Seed $seed -Name ("R2_seed_{0}" -f $seed)
        $seedMetricPaths += Join-Path $evaluationPath "metrics.json"
    }
    $r2Output = Join-Path $experimentPath "R2\seed_summary.json"
    & $python (Join-Path $projectRoot "scripts\aggregate_h120_ranker_phase_c.py") `
        --protocol $protocol `
        --seed-metrics $seedMetricPaths `
        --output $r2Output
    if ($LASTEXITCODE -ne 0) { throw "R2 aggregation failed" }

    $r3Output = Join-Path $experimentPath "R3"
    & $python (Join-Path $projectRoot "scripts\tune_h120_ranker_inner.py") `
        --dataset-run $datasetPath `
        --trials $R3Trials `
        --output $r3Output
    if ($LASTEXITCODE -ne 0) { throw "R3 tuning failed" }

    Write-Host "Phase C complete for research only."
    Write-Host "R1 metrics: $(Join-Path $r1Path 'metrics.json')"
    Write-Host "R2 summary: $r2Output"
    Write-Host "R3 trials: $(Join-Path $r3Output 'trials.jsonl')"
    Write-Host "Do not freeze/refit or open the holdout until artifacts are reviewed."
}
finally {
    Pop-Location
}
