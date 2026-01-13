# Azure Cost Analysis

Generate a comprehensive cost breakdown of Azure subscription resources.

## Prerequisites

Ensure Azure CLI is authenticated: `az account show`

## Process

### 1. Get Cost Data

Fetch cost data for the specified period (default: last 30 days):

```bash
# Current billing period costs by resource group
az cost query --type ActualCost --dataset-grouping name=ResourceGroup type=Dimension --timeframe MonthToDate

# Daily cost trend
az cost query --type ActualCost --dataset-grouping name=ServiceName type=Dimension --timeframe MonthToDate --dataset-aggregation totalCost=Sum

# Forecast for current month
az cost query --type AmortizedCost --timeframe MonthToDate
```

### 2. Resource Group Breakdown

For each resource group, show:
- Total cost MTD
- Top 3 cost drivers (specific resources)
- Cost trend (increasing/decreasing/stable)
- Percentage of total spend

### 3. Service Category Analysis

Break down by service type:
- Compute (VMs, Container Apps, Functions)
- Storage (Blob, Cosmos DB, SQL)
- AI Services (OpenAI, Cognitive Services)
- Networking (Bandwidth, Load Balancers)
- Other

### 4. Anomaly Detection

Flag any of these conditions:
- Daily cost spike > 20% above 7-day average
- New resources appearing that weren't present last week
- Resources with zero usage but ongoing cost (idle resources)
- Resources approaching quota limits

### 5. Optimization Suggestions

Based on usage patterns, suggest:
- Underutilized resources that could be downsized
- Reserved instance opportunities for consistent workloads
- Dev/test resources that could use B-series VMs
- Storage tier optimizations (hot vs cool vs archive)

## Output Format

```
## Azure Cost Summary (MTD)

Total Spend: $X,XXX.XX
Forecast End of Month: $X,XXX.XX
vs Last Month: +/- XX%

### By Resource Group
| Resource Group | Cost | % of Total | Trend |
|---------------|------|------------|-------|
| ... | ... | ... | ... |

### Top Cost Drivers
1. [Resource Name] - $XXX.XX (reason)
2. ...

### Alerts
- [Any anomalies or concerns]

### Optimization Opportunities
- [Specific actionable suggestions]
```

## Arguments

- `$ARGUMENTS` - Optional: "daily" for daily breakdown, "weekly" for weekly, or resource group name to filter
