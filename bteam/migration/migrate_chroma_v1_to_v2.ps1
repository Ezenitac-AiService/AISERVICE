[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:18000",
    [string]$MySqlContainer = "bteam-green-mysql-green-1",
    [int]$BatchSize = 500,
    [int]$MaxBatches = 0
)

$ErrorActionPreference = "Stop"
$headers = @{ "Content-Type" = "application/json" }
$collectionUrl = "$BaseUrl/api/v2/tenants/default_tenant/databases/default_database/collections"
$collections = Invoke-RestMethod -Uri $collectionUrl
$legacy = @($collections | Where-Object { $_.name -eq "oliview_review_sentences" })
$target = @($collections | Where-Object { $_.name -eq "oliview_review_sentences_v2" })
if ($legacy.Count -ne 1 -or $target.Count -ne 1) {
    throw "Expected exactly one legacy and one v2 collection"
}

$mapQuery = "SELECT aspect_sentence_id, review_id FROM cosmetic_db.review_aspect_sentences"
$mapLines = @(docker exec $MySqlContainer mysql -uroot -predacted -N -e $mapQuery)
$reviewBySentence = @{}
foreach ($line in $mapLines) {
    $parts = $line -split "`t"
    if ($parts.Count -eq 2) {
        $reviewBySentence[[int64]$parts[0]] = [int64]$parts[1]
    }
}

$countUri = "$collectionUrl/$($legacy.id)/count"
$total = [int](Invoke-RestMethod -Uri $countUri)
$sourceGetUri = "$collectionUrl/$($legacy.id)/get"
$targetUpsertUri = "$collectionUrl/$($target.id)/upsert"
$migrated = 0
$batchNumber = 0

for ($offset = 0; $offset -lt $total; $offset += $BatchSize) {
    if ($MaxBatches -gt 0 -and $batchNumber -ge $MaxBatches) {
        break
    }
    $body = @{
        limit = [Math]::Min($BatchSize, $total - $offset)
        offset = $offset
        include = @("documents", "metadatas", "embeddings")
    } | ConvertTo-Json -Depth 10 -Compress
    $batch = Invoke-RestMethod -Method Post -Uri $sourceGetUri -Headers $headers -Body $body
    $ids = @($batch.ids)
    if ($ids.Count -eq 0) {
        throw "Legacy collection returned no rows at offset $offset"
    }

    $newMetadata = @()
    foreach ($id in $ids) {
        $sentenceId = [int64]$id
        if (-not $reviewBySentence.ContainsKey($sentenceId)) {
            throw "No SQL review mapping for aspect_sentence_id=$sentenceId"
        }
        $meta = @{}
        $originalIndex = [Array]::IndexOf($ids, $id)
        if ($null -ne $batch.metadatas -and $null -ne $batch.metadatas[$originalIndex]) {
            foreach ($property in $batch.metadatas[$originalIndex].PSObject.Properties) {
                if ($null -ne $property.Value) {
                    $meta[$property.Name] = $property.Value
                }
            }
        }
        $meta["source_review_id"] = [int64]$reviewBySentence[$sentenceId]
        $meta["review_id"] = [int64]$reviewBySentence[$sentenceId]
        $meta["aspect_sentence_id"] = $sentenceId
        $newMetadata += $meta
    }

    $upsert = @{
        ids = @($ids | ForEach-Object { [string]$_ })
        embeddings = @($batch.embeddings)
        documents = @($batch.documents)
        metadatas = $newMetadata
    } | ConvertTo-Json -Depth 20 -Compress
    Invoke-RestMethod -Method Post -Uri $targetUpsertUri -Headers $headers -Body $upsert | Out-Null
    $migrated += $ids.Count
    $batchNumber++
    if ($migrated % ($BatchSize * 10) -eq 0 -or $migrated -eq $total) {
        Write-Host "migrated=$migrated/$total"
    }
}

Write-Host "legacy_count=$total"
Write-Host "v2_count=$([int](Invoke-RestMethod -Uri "$collectionUrl/$($target.id)/count"))"
