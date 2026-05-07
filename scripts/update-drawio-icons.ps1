# Embed Azure icons into drawio file as URL-encoded inline SVG (data:image/svg+xml,...).
# Avoids base64 because the ';' in 'data:image/svg+xml;base64,...' breaks drawio style parsing.
# Reads SVG files from docs/assets/azure-icons/ and embeds them inline so the diagram is portable.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$drawio = Join-Path $root 'docs\design-infrastructure-diagram.drawio'
$iconRoot = Join-Path $root 'docs\assets\azure-icons'

# shape key -> [category, filename]
$mapping = @{
    'user'    = @('identity','Users.svg')
    'mi'      = @('identity','Managed_Identities.svg')
    'fe'      = @('containers','Container_Apps.svg')
    'be'      = @('containers','Container_Apps.svg')
    'cae_env' = @('containers','Container_Apps_Environments.svg')
    'acr'     = @('containers','Container_Registries.svg')
    'pe'      = @('networking','Private_Endpoint.svg')
    'pdns'    = @('networking','DNS_Zones.svg')
    'aif'     = @('ai_machine_learning','AI_Studio.svg')
    'cog'     = @('ai_machine_learning','Cognitive_Services.svg')
    'st'      = @('storage','Storage_Accounts.svg')
    'law'     = @('management_governance','Log_Analytics_Workspaces.svg')
}

# mxCell id -> shape key
$idToShape = @{
    'user'='user'; 'fe'='fe'; 'be'='be'; 'cae_icon'='cae_env'; 'pe'='pe'; 'proj'='aif'; 'gpt'='cog'; 'sp'='cog'; 'st'='st'; 'acr'='acr'; 'law'='law'
    'net'='user';  'fe2'='fe'; 'be2'='be'; 'pe2'='pe'; 'pdns'='pdns'; 'st2'='st'
    'bemi'='mi';   'be3'='be'; 'st3'='st'; 'proj3'='aif'; 'gpt3'='cog'
}

# Cache: shape key -> data URI
$dataUriCache = @{}
function Get-DataUri([string]$shapeKey) {
    if ($dataUriCache.ContainsKey($shapeKey)) { return $dataUriCache[$shapeKey] }
    $cat, $file = $mapping[$shapeKey]
    $path = Join-Path $iconRoot (Join-Path $cat $file)
    if (-not (Test-Path $path)) { throw "Missing icon: $path" }
    $svg = Get-Content -Path $path -Raw -Encoding UTF8
    # Compact whitespace
    $svg = ($svg -replace "`r?`n", ' ') -replace '\s+', ' '
    # URL-encode using .NET (encodes ';', '"', '<', '>', '#', etc.)
    $encoded = [System.Uri]::EscapeDataString($svg)
    $uri = "data:image/svg+xml,$encoded"
    $dataUriCache[$shapeKey] = $uri
    return $uri
}

# Verify icons exist
foreach ($k in $mapping.Keys) {
    $cat, $file = $mapping[$k]
    $p = Join-Path $iconRoot (Join-Path $cat $file)
    if (Test-Path $p) { Write-Host "Exists     $cat/$file" } else { Write-Host "MISSING    $cat/$file" -ForegroundColor Red }
}

$content = Get-Content -Path $drawio -Raw -Encoding UTF8
$count = 0
foreach ($id in $idToShape.Keys) {
    $shape = $idToShape[$id]
    $uri = Get-DataUri $shape

    $pattern = '(<mxCell\s+id="' + [Regex]::Escape($id) + '"[^>]*?\sstyle=")([^"]*)(")'
    $m = [Regex]::Match($content, $pattern)
    if (-not $m.Success) {
        Write-Host "MISS  id=$id" -ForegroundColor Yellow
        continue
    }
    $style = $m.Groups[2].Value
    # Strip prior image-related fragments
    $style = $style -replace 'shape=image;', ''
    $style = $style -replace 'shape=mxgraph\.azure2\.[^;]+;', ''
    $style = $style -replace 'imageAspect=\d+;', ''
    $style = $style -replace 'aspect=fixed;', ''
    $style = $style -replace 'image=[^;"]*;', ''
    # Remove any leftover image=... at end without trailing ;
    $style = $style -replace 'image=[^;"]*$', ''
    if ($style -and -not $style.EndsWith(';')) { $style += ';' }
    $newStyle = "${style}shape=image;imageAspect=0;aspect=fixed;image=$uri;"
    $replacement = $m.Groups[1].Value + $newStyle + $m.Groups[3].Value
    $content = $content.Substring(0, $m.Index) + $replacement + $content.Substring($m.Index + $m.Length)
    $count++
    Write-Host "OK    id=$id -> $shape (uri len=$($uri.Length))"
}

Set-Content -Path $drawio -Value $content -Encoding UTF8 -NoNewline
Write-Host "Updated $drawio (cells rewritten: $count)" -ForegroundColor Green
