<#
.SYNOPSIS
    Manage the MARP workspace: clone, inspect and update every component
    repository listed in services/repos.yml.

.DESCRIPTION
    The MARP ecosystem is a polyrepo. This umbrella repository holds the
    workspace layout and the component registry, but each component is its own
    independent Git repository cloned as a subdirectory here. That gives one
    place from which every interconnected project is reachable -- by a
    developer or by an agent -- without merging their histories.

    This script is what turns a fresh clone of the umbrella into that
    workspace. It reads services/repos.yml, which is the single source of truth
    for what exists and where it belongs, so adding a component means editing
    the registry and the .gitignore rather than editing this script.

    Commands:

      list      What the registry declares, and whether it is present here.
      clone     Clone whatever is missing. Never touches what is already there.
      status    Branch, uncommitted changes and drift from upstream, per repo.
      pull      Fast-forward every clean repository. Skips dirty ones.
      doctor    Check the workspace is sound, and in particular that the
                umbrella cannot absorb a component.

.PARAMETER Command
    One of list, clone, status, pull, doctor. Defaults to list, because it is
    the only one that cannot surprise you.

.PARAMETER Group
    Restrict to components (part of a MARP deployment) or related (developed
    alongside, but not part of one). Defaults to all.

.PARAMETER Protocol
    https (default) or ssh. https works with a credential helper or a token;
    ssh needs a key on the account. Only affects new clones.

.EXAMPLE
    .\scripts\marp.ps1 clone
    Clone every registered repository that is not already present.

.EXAMPLE
    .\scripts\marp.ps1 clone -Group components -Protocol ssh
    Clone only the deployment components, over SSH.

.NOTES
    Author: Isaac Travers
    Windows counterpart of scripts/marp.sh. The two must stay behaviourally
    identical; the registry they read is shared.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('list', 'clone', 'status', 'pull', 'doctor')]
    [string]$Command = 'list',

    [ValidateSet('all', 'components', 'related')]
    [string]$Group = 'all',

    [ValidateSet('https', 'ssh')]
    [string]$Protocol = 'https'
)

$ErrorActionPreference = 'Stop'

# The umbrella root is the parent of this script's directory. Deriving it
# rather than trusting the current directory means the script works when it is
# invoked from anywhere, including from inside a component.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RegistryPath = Join-Path $RepoRoot 'services\repos.yml'

# Directory names components used to have. Kept only so a part-migrated
# checkout is reported clearly instead of looking like a missing repository.
$LegacyDirectories = @{ 'MARE_API' = 'MARP_API' }

$script:Failures = 0

function Write-Fail { param([string]$Message) $script:Failures++; Write-Host "  FAIL  $Message" -ForegroundColor Red }
function Write-Warn { param([string]$Message) Write-Host "  WARN  $Message" -ForegroundColor Yellow }
function Write-Pass { param([string]$Message) Write-Host "  ok    $Message" -ForegroundColor DarkGray }

<#
.SYNOPSIS
    Read services/repos.yml into an ordered list of registry entries.

.DESCRIPTION
    Deliberately not a YAML parser. Windows PowerShell 5.1 ships without one,
    and requiring a module before the workspace even exists would defeat the
    point of a bootstrap script. Instead the registry's shape is constrained
    and documented in its own header: group keys at column 0, a repository key
    at two spaces, its fields at four, and folded values running on at six or
    more. Anything else is ignored rather than guessed at, and doctor fails on
    an entry it could not read -- so a registry edit that breaks this surfaces
    as a check failure rather than as a silently skipped repository.
#>
function Read-Registry {
    if (-not (Test-Path -LiteralPath $RegistryPath)) {
        throw "Component registry not found at $RegistryPath"
    }

    $entries = New-Object System.Collections.ArrayList
    # Named currentGroup rather than group on purpose: PowerShell variable
    # names are case-insensitive, so a local $group would shadow the -Group
    # parameter and the filter below would silently match whichever group the
    # file happened to end on.
    $currentGroup = $null
    $current = $null

    foreach ($line in Get-Content -LiteralPath $RegistryPath) {
        if ($line -match '^\s*#') { continue }

        if ($line -match '^(components|related):\s*$') {
            $currentGroup = $Matches[1]
            $current = $null
            continue
        }

        if ($null -eq $currentGroup) { continue }

        if ($line -match '^  ([A-Za-z0-9_.-]+):\s*$') {
            $current = [ordered]@{ name = $Matches[1]; group = $currentGroup }
            [void]$entries.Add($current)
            continue
        }

        if ($null -ne $current -and $line -match '^    ([a-z_]+):\s*(.*)$') {
            $value = $Matches[2].Trim()
            # A folded or literal block marker carries no value of its own.
            if ($value -eq '>' -or $value -eq '|' -or $value -eq '') { continue }
            $current[$Matches[1]] = $value
        }
    }

    if ($Group -ne 'all') {
        return @($entries | Where-Object { $_.group -eq $Group })
    }
    return @($entries)
}

<#
.SYNOPSIS
    Reduce a Git remote URL to owner/name so two spellings can be compared.

.DESCRIPTION
    The same repository is reached as https://github.com/Org/Name.git, as
    git@github.com:Org/Name.git, and with or without the .git suffix. Comparing
    raw URLs would report a false mismatch for a clone that is perfectly
    correct but was made over the other protocol.
#>
function Get-RemoteSlug {
    param([string]$Url)
    if ([string]::IsNullOrWhiteSpace($Url)) { return $null }
    $slug = $Url.Trim()
    $slug = $slug -replace '\.git$', ''
    $slug = $slug -replace '^git@[^:]+:', ''
    $slug = $slug -replace '^ssh://git@[^/]+/', ''
    $slug = $slug -replace '^https?://[^/]+/', ''
    return $slug.Trim('/')
}

function Get-CloneUrl {
    param([string]$Repository)
    if ($Protocol -eq 'ssh') { return "git@github.com:$Repository.git" }
    return "https://github.com/$Repository.git"
}

function Get-EntryPath {
    param($Entry)
    return (Join-Path $RepoRoot $Entry.directory)
}

<#
.SYNOPSIS
    True when a registry entry names a repository that actually exists.

.DESCRIPTION
    The registry allows `repository: null` for a component that is planned but
    not yet created, so that the layout can be documented before the code
    exists. Those entries are real registry content, not errors, and every
    command has to step over them rather than try to clone "null".
#>
function Test-Clonable {
    param($Entry)
    return -not ([string]::IsNullOrWhiteSpace($Entry.repository) -or $Entry.repository -eq 'null')
}

function Invoke-Git {
    param([string]$Directory, [string[]]$Arguments)
    $output = & git -C $Directory @Arguments 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = ($output -join [Environment]::NewLine).Trim() }
}

function Get-FirstLine {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return '' }
    return ($Text -split "`r?`n")[0]
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

function Invoke-List {
    param($Entries)

    $rows = foreach ($entry in $Entries) {
        $path = Get-EntryPath $entry
        $present = 'no'
        if (Test-Path -LiteralPath (Join-Path $path '.git')) { $present = 'yes' }
        elseif (Test-Path -LiteralPath $path) { $present = 'not a repo' }

        [pscustomobject]@{
            Group      = $entry.group
            Name       = $entry.name
            Repository = if (Test-Clonable $entry) { $entry.repository } else { '(not created)' }
            Directory  = $entry.directory
            Branch     = $entry.default_branch
            Visibility = $entry.visibility
            Present    = $present
        }
    }

    $rows | Format-Table -AutoSize
    Write-Host "Registry: $RegistryPath"
}

function Invoke-Clone {
    param($Entries)

    foreach ($entry in $Entries) {
        $path = Get-EntryPath $entry

        if (-not (Test-Clonable $entry)) {
            Write-Warn "$($entry.name): no repository yet, nothing to clone"
            continue
        }

        if (Test-Path -LiteralPath (Join-Path $path '.git')) {
            Write-Pass "$($entry.directory): already cloned"
            continue
        }

        # A directory that exists without a .git is either a half-finished
        # clone or somebody's unrelated files. Cloning into it would either
        # fail messily or bury whatever is there, so stop and say so.
        if (Test-Path -LiteralPath $path) {
            Write-Fail "$($entry.directory): exists but is not a Git repository; refusing to clone over it"
            continue
        }

        $url = Get-CloneUrl $entry.repository
        Write-Host "Cloning $($entry.repository) -> $($entry.directory) ($($entry.default_branch))" -ForegroundColor Cyan

        $arguments = @('clone')
        if ($entry.default_branch) { $arguments += @('--branch', $entry.default_branch) }
        $arguments += @($url, $path)

        & git @arguments
        if ($LASTEXITCODE -ne 0) {
            $hint = if ($entry.visibility -eq 'private') { ' (private repository: check your credentials)' } else { '' }
            Write-Fail "$($entry.directory): clone failed$hint"
        }
    }

    if ($script:Failures -eq 0) {
        Write-Host ''
        Write-Host 'Workspace ready. Open marp.code-workspace, or run: .\scripts\marp.ps1 doctor' -ForegroundColor Green
    }
}

function Invoke-Status {
    param($Entries)

    $rows = foreach ($entry in $Entries) {
        $path = Get-EntryPath $entry
        if (-not (Test-Path -LiteralPath (Join-Path $path '.git'))) {
            [pscustomobject]@{ Directory = $entry.directory; Branch = '-'; Changes = '-'; Upstream = 'not cloned' }
            continue
        }

        $branch = (Invoke-Git $path @('rev-parse', '--abbrev-ref', 'HEAD')).Output
        $dirty = (Invoke-Git $path @('status', '--porcelain')).Output
        $changes = if ($dirty) { ($dirty -split "`r?`n").Count } else { 0 }

        # No upstream is normal for a local-only branch, so it is reported
        # rather than treated as a problem.
        $counts = Invoke-Git $path @('rev-list', '--left-right', '--count', 'HEAD...@{u}')
        $upstream = if ($counts.ExitCode -ne 0) {
            'no upstream'
        } else {
            $parts = $counts.Output -split '\s+'
            "ahead $($parts[0]), behind $($parts[1])"
        }

        [pscustomobject]@{ Directory = $entry.directory; Branch = $branch; Changes = $changes; Upstream = $upstream }
    }

    $rows | Format-Table -AutoSize
}

function Invoke-Pull {
    param($Entries)

    foreach ($entry in $Entries) {
        $path = Get-EntryPath $entry
        if (-not (Test-Path -LiteralPath (Join-Path $path '.git'))) {
            Write-Warn "$($entry.directory): not cloned"
            continue
        }

        # Pulling over uncommitted work is how someone loses an afternoon.
        # Fast-forward only, and only when there is nothing to lose.
        if ((Invoke-Git $path @('status', '--porcelain')).Output) {
            Write-Warn "$($entry.directory): uncommitted changes, skipped"
            continue
        }

        $result = Invoke-Git $path @('pull', '--ff-only')
        if ($result.ExitCode -eq 0) {
            Write-Pass "$($entry.directory): $(Get-FirstLine $result.Output)"
        } else {
            Write-Fail "$($entry.directory): $(Get-FirstLine $result.Output)"
        }
    }
}

<#
.SYNOPSIS
    Check the workspace is sound, and that the umbrella cannot absorb a
    component repository.

.DESCRIPTION
    The check that matters most is the ignore check. Every component lives as a
    directory inside this repository, so if one stops being ignored then a
    commit here quietly picks up either its files or a gitlink pointing at it.
    Neither belongs in the umbrella's history, and both are awkward to undo
    later. Verifying it is cheap, so it is verified rather than assumed.
#>
function Invoke-Doctor {
    param($Entries)

    Write-Host 'Git' -ForegroundColor Cyan
    $gitVersion = (& git --version 2>&1) -join ''
    if ($LASTEXITCODE -eq 0) { Write-Pass $gitVersion } else { Write-Fail 'git is not on PATH' }

    Write-Host 'Registry' -ForegroundColor Cyan
    if ($Entries.Count -eq 0) {
        Write-Fail "no entries read from $RegistryPath -- has its layout changed?"
    } else {
        Write-Pass "$($Entries.Count) entries read"
    }
    foreach ($entry in $Entries) {
        foreach ($field in @('directory', 'default_branch')) {
            if (-not $entry[$field]) { Write-Fail "$($entry.name): registry entry has no $field" }
        }
    }

    Write-Host 'Umbrella ignores every component directory' -ForegroundColor Cyan
    foreach ($entry in $Entries) {
        if (-not $entry.directory) { continue }
        & git -C $RepoRoot check-ignore --quiet -- "$($entry.directory)/" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Pass "$($entry.directory)/ is ignored"
        } else {
            Write-Fail "$($entry.directory)/ is NOT ignored -- add it to .gitignore before committing here"
        }
    }

    Write-Host 'Component clones' -ForegroundColor Cyan
    foreach ($entry in $Entries) {
        $path = Get-EntryPath $entry
        if (-not (Test-Path -LiteralPath $path)) {
            Write-Warn "$($entry.directory): not cloned (run: .\scripts\marp.ps1 clone)"
            continue
        }
        if (-not (Test-Path -LiteralPath (Join-Path $path '.git'))) {
            Write-Fail "$($entry.directory): present but not a Git repository"
            continue
        }
        if (-not (Test-Clonable $entry)) { continue }

        $actual = Get-RemoteSlug (Invoke-Git $path @('remote', 'get-url', 'origin')).Output
        $expected = Get-RemoteSlug $entry.repository
        if ($actual -eq $expected) {
            Write-Pass "$($entry.directory): origin is $expected"
        } else {
            Write-Fail "$($entry.directory): origin is $actual, registry says $expected"
        }
    }

    Write-Host 'Former directory names' -ForegroundColor Cyan
    $anyLegacy = $false
    foreach ($legacy in $LegacyDirectories.Keys) {
        if (Test-Path -LiteralPath (Join-Path $RepoRoot $legacy)) {
            $anyLegacy = $true
            Write-Warn "$legacy/ is still here; it was renamed to $($LegacyDirectories[$legacy])/ -- rename it so the workspace file and the registry find it"
        }
    }
    if (-not $anyLegacy) { Write-Pass 'none present' }

    Write-Host 'Umbrella working tree' -ForegroundColor Cyan
    $visible = (Invoke-Git $RepoRoot @('status', '--porcelain')).Output
    $leaked = @()
    foreach ($entry in $Entries) {
        if ($entry.directory -and $visible -match [regex]::Escape($entry.directory)) { $leaked += $entry.directory }
    }
    if ($leaked.Count -gt 0) {
        Write-Fail "the umbrella sees changes under $($leaked -join ', ') -- a commit here would carry them"
    } else {
        Write-Pass 'no component paths visible to the umbrella'
    }

    Write-Host ''
    if ($script:Failures -eq 0) {
        Write-Host 'Workspace looks sound.' -ForegroundColor Green
    } else {
        Write-Host "$($script:Failures) problem(s) found." -ForegroundColor Red
    }
}

# ---------------------------------------------------------------------------

$entries = Read-Registry

switch ($Command) {
    'list'   { Invoke-List   $entries }
    'clone'  { Invoke-Clone  $entries }
    'status' { Invoke-Status $entries }
    'pull'   { Invoke-Pull   $entries }
    'doctor' { Invoke-Doctor $entries }
}

if ($script:Failures -gt 0) { exit 1 } else { exit 0 }
