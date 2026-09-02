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

      setup     Everything: clone, install marp-api's dependencies, write its
                .env, build a database with the schema, give the first
                administrator a password, and hand the annotation GUI an
                application token. Idempotent -- skips what is already done.
      clone     Clone whatever is missing. Never touches what is already
                there. The default, because it is what this script is for.
      list      What the registry declares, and whether it is present here.
      status    Branch, uncommitted changes and drift from upstream, per repo.
      pull      Fast-forward every clean repository. Skips dirty ones.
      doctor    Check the workspace is sound, and in particular that the
                umbrella cannot absorb a component.
      db        Provision and run the PostgreSQL database that marp-api needs.
                Delegates to scripts/db.ps1 -- see `marp db` subcommands
                up, down, status, env and destroy.

.PARAMETER Command
    One of setup, clone, list, status, pull, doctor, db. Defaults to clone: it is the
    reason this script exists, and it is safe to repeat -- it skips whatever is
    already present and refuses to write into a directory it did not create.

.PARAMETER Component
    A single repository to act on, by registry name (marp-api) or by directory
    (MARP_API), case-insensitively. Both spellings are accepted because both
    are what people have in front of them. Omit it to act on everything.

    When Command is `db`, this is the database subcommand instead.

.PARAMETER Group
    Restrict to components (part of a MARP deployment) or related (developed
    alongside, but not part of one). Defaults to all.

.PARAMETER Protocol
    https (default) or ssh. https works with a credential helper or a token;
    ssh needs a key on the account. Only affects new clones.

.EXAMPLE
    .\scripts\marp.ps1 setup
    Go from a bare clone of this repository to a database marp-api can use.

.EXAMPLE
    .\scripts\marp.ps1
    Clone every registered repository that is not already present.

.EXAMPLE
    .\scripts\marp.ps1 clone marp-api
    Clone just that one.

.EXAMPLE
    .\scripts\marp.ps1 status marp-video-player
    Report on one repository rather than all of them.

.EXAMPLE
    .\scripts\marp.ps1 clone -Group components -Protocol ssh
    Clone only the deployment components, over SSH.

.EXAMPLE
    .\scripts\marp.ps1 db up
    Download, start and populate the PostgreSQL database marp-api needs.

.NOTES
    Author: Isaac Travers
    Windows counterpart of scripts/marp.sh. The two must stay behaviourally
    identical; the registry they read is shared.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('setup', 'clone', 'list', 'status', 'pull', 'doctor', 'db')]
    [string]$Command = 'clone',

    # For most commands this narrows the work to one repository. For `db` it is
    # the database subcommand -- up, down, status, env, destroy.
    [Parameter(Position = 1)]
    [string]$Component,

    [ValidateSet('all', 'components', 'related')]
    [string]$Group = 'all',

    [ValidateSet('https', 'ssh')]
    [string]$Protocol = 'https',

    # Passed through to scripts/db.ps1 by the `db` command.
    [int]$Port = 5432,
    [string]$Password = 'marp_dev_password',

    # setup only. The first administrator's display name reaches the bootstrap
    # migration through .env, so it has to be decided before the database is
    # built rather than after.
    [string]$AdminName = $env:USERNAME,
    [string]$AdminUsername = $env:USERNAME,

    # Prompted for when omitted. Pass it to run setup unattended.
    [string]$AdminPassword,

    # Skip creating the application token for the annotation GUI.
    [switch]$NoToken
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

<#
.SYNOPSIS
    Run an external command without its stderr becoming a fatal error.

.DESCRIPTION
    Windows PowerShell with $ErrorActionPreference = 'Stop' turns anything a
    native executable writes to stderr into a terminating error, regardless of
    its exit code. npm writes ordinary notices there, so `npx sequelize-cli
    db:migrate` aborted this script the moment npm mentioned a new version was
    available -- a failure with no failure in it, and an intermittent one,
    since it depended on whether npm felt talkative.

    So the preference is relaxed for the duration of the call and the exit code
    is what gets believed, which is the only thing that actually reports
    success.

    The exit code is left in $script:LastNativeExit rather than returned, and
    the command's own output goes to the host rather than down the pipeline --
    both because a PowerShell function returns everything it emits, so mixing
    them makes each unusable.

.OUTPUTS
    None.
#>
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$Command,
        [string[]]$Arguments = @()
    )

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Out-Host, not the success stream: a function's uncaptured output
        # becomes its return value, so letting npm's chatter through made
        # `return $false` into an array -- and an array is truthy, so a failure
        # reported itself as success on the very next line.
        & $Command @Arguments | Out-Host
        $script:LastNativeExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

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
        $entries = @($entries | Where-Object { $_.group -eq $Group })
    }

    # A single repository, named either way round. People have the directory in
    # front of them in a file explorer and the registry name in front of them
    # in repos.yml, so both are accepted rather than making them look it up.
    if ($Component) {
        $wanted = @($entries | Where-Object {
            $_.name -eq $Component -or $_.directory -eq $Component
        })
        if ($wanted.Count -eq 0) {
            $known = ($entries | ForEach-Object { $_.name }) -join ', '
            throw "No repository called '$Component'. Known: $known"
        }
        return $wanted
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

<#
.SYNOPSIS
    Print the next thing to do, based on what has actually been done.

.DESCRIPTION
    A cloned workspace is not a working one, and "Workspace ready" used to be
    the last thing this script said -- leaving someone with five repositories,
    no database, and no indication that anything remained. Somebody who has
    just cloned does not know that marp-api needs its dependencies installed
    before `db up` can load a schema, or that the API will not start without a
    session secret.

    So rather than a static list of instructions to read past, this inspects
    the workspace and prints only what is still outstanding, in the order it
    has to happen. When everything is done it says so and stops talking.
#>
function Show-NextSteps {
    # setup runs clone as its first step and then does everything the list
    # would tell someone to do, so printing it there describes work already
    # under way.
    if ($script:SuppressNextSteps) { return }

    $apiDir  = Join-Path $RepoRoot 'MARP_API'
    $steps   = New-Object System.Collections.ArrayList

    if (-not (Test-Path -LiteralPath (Join-Path $apiDir 'package.json'))) {
        [void]$steps.Add(@('Clone marp-api', '.\scripts\marp.ps1 clone marp-api'))
    } else {
        # Before the database, because `db up` loads the schema by running
        # marp-api's own scripts and cannot without its dependencies.
        if (-not (Test-Path -LiteralPath (Join-Path $apiDir 'node_modules'))) {
            [void]$steps.Add(@("Install marp-api's dependencies", 'cd MARP_API; npm install; cd ..'))
        }

        $clusterReady = Test-Path -LiteralPath (Join-Path $RepoRoot '.postgres\data\PG_VERSION')
        $listening = $false
        try { $listening = [bool](Get-NetTCPConnection -State Listen -LocalPort 5432 -ErrorAction Stop) } catch { }
        if (-not ($clusterReady -and $listening)) {
            [void]$steps.Add(@('Start a database and load the schema', '.\scripts\marp.ps1 db up'))
        }

        if (-not (Test-Path -LiteralPath (Join-Path $apiDir '.env'))) {
            [void]$steps.Add(@("Create marp-api's configuration", 'cd MARP_API; Copy-Item .env.example .env'))
            [void]$steps.Add(@('Put the DB_* lines from `db up` into MARP_API\.env, and set',
                               'AUTH_SESSION_SECRET  (any long random string)'))
        }

        [void]$steps.Add(@('Run the API at http://localhost:3000', 'cd MARP_API; npm run dev'))
    }

    Write-Host ''
    Write-Host 'Next:' -ForegroundColor Cyan

    # More than one outstanding step means setup can do all of them, and
    # listing five commands invites someone to run them by hand instead.
    if ($steps.Count -gt 1) {
        Write-Host '  Everything below in one command:'
        Write-Host '       .\scripts\marp.ps1 setup' -ForegroundColor DarkGray
        Write-Host ''
    }

    $number = 1
    foreach ($step in $steps) {
        Write-Host ("  {0}. {1}" -f $number, $step[0])
        Write-Host ("       {0}" -f $step[1]) -ForegroundColor DarkGray
        $number++
    }
    Write-Host ''
    Write-Host '  Full walkthrough: README.md, "Getting the whole workspace".' -ForegroundColor DarkGray
}

<#
.SYNOPSIS
    Set one key in a .env file, leaving every other line alone.

.DESCRIPTION
    Rewrites the key's assignment in place, and appends it if the file has
    none. Everything else -- comments, ordering, unrelated settings -- survives
    untouched, because marp-api's .env also holds Jellyfin credentials and
    reporting connection details that nothing here has any business rewriting.

    Only uncommented assignments are matched, and this is the whole subtlety.
    An earlier version also un-commented lines beginning with the key, which
    seemed helpful until it rewrote this line of .env.example's prose:

        # DB_PORT=5433.

    That is documentation about the virtual machine's port forward, not a
    setting -- so DB_PORT was "set" in a comment while the real assignment
    below it kept its old value, and the API would have quietly gone on
    connecting to the wrong database. A commented-out setting and a comment
    that happens to mention one are indistinguishable, so neither is touched.

    Appending when there is no assignment is safe: dotenv resolves a duplicated
    key to its last occurrence, verified rather than assumed.
#>
function Set-EnvValue {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Key,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Value
    )

    $lines = @(Get-Content -LiteralPath $Path)
    $pattern = "^\s*$([regex]::Escape($Key))\s*="
    $replaced = $false

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = "$Key=$Value"
            $replaced = $true
            break
        }
    }

    if (-not $replaced) { $lines += "$Key=$Value" }
    Set-Content -LiteralPath $Path -Value $lines -Encoding ascii
}

<#
.SYNOPSIS
    Read one key's current value from a .env file.

.OUTPUTS
    System.String, or $null when the key is absent or commented out.
#>
function Get-EnvValue {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Key)

    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)$") { return $Matches[1].Trim() }
    }
    return $null
}

<#
.SYNOPSIS
    Everything from a bare clone to a database marp-api can talk to.

.DESCRIPTION
    The steps this runs were, until now, a list printed for someone to carry
    out by hand -- install dependencies, provision a database, copy a template,
    paste six settings, invent a session secret. None of that needed a human:
    the values all come from the database that was just created, and a
    development secret is random bytes.

    Idempotent by construction. Anything already done is skipped and reported,
    so running it twice is a no-op rather than a reset. It deliberately stops
    short of starting the API, which is a long-running process someone should
    choose to start themselves.
#>
function Invoke-Setup {
    param($Entries)

    $script:SuppressNextSteps = $true
    Invoke-Clone $Entries
    $script:SuppressNextSteps = $false

    if ($script:Failures -gt 0) {
        Write-Host ''
        Write-Host 'Stopping: not every repository could be cloned.' -ForegroundColor Red
        return
    }

    $apiDir = Join-Path $RepoRoot 'MARP_API'
    if (-not (Test-Path -LiteralPath (Join-Path $apiDir 'package.json'))) {
        Write-Fail 'MARP_API is not present, so there is nothing to configure.'
        return
    }

    foreach ($tool in @('node', 'npm')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            Write-Fail "$tool is not on PATH. Node comes from nvm-windows here; open a new terminal, or prepend C:/nvm4w/nodejs to PATH."
            return
        }
    }

    # Dependencies first: the database step finishes by having marp-api load
    # its schema, which it cannot do without them.
    if (Test-Path -LiteralPath (Join-Path $apiDir 'node_modules')) {
        Write-Pass 'MARP_API dependencies already installed'
    } else {
        Write-Host 'Installing MARP_API dependencies' -ForegroundColor Cyan
        Push-Location $apiDir
        try { Invoke-Native 'npm' @('install') } finally { Pop-Location }
        if ($script:LastNativeExit -ne 0) {
            Write-Fail 'npm install failed. On Windows the native argon2 build needs the Visual Studio C++ build tools.'
            return
        }
    }

    # Configuration before the database, and this ordering is load-bearing. The
    # bootstrap migration names the first administrator from
    # BOOTSTRAP_ADMIN_NAME, which it reads from .env -- so writing .env
    # afterwards, as this used to, meant the migration had already fallen back
    # to a generic default and the name arrived too late to have any effect.
    Write-Host ''
    Write-Host 'Configuring MARP_API\.env' -ForegroundColor Cyan
    if (-not (Set-ApiEnvironment -ApiDir $apiDir)) { return }

    Write-Host ''
    & (Join-Path $PSScriptRoot 'db.ps1') up -Port $Port -Password $Password -Quiet
    if ($LASTEXITCODE -ne 0) { Write-Fail 'The database could not be prepared.'; return }

    Write-Host ''
    Write-Host 'First administrator' -ForegroundColor Cyan
    $loginReady = Set-FirstAdministrator -ApiDir $apiDir

    $token = $null
    if (-not $NoToken) {
        Write-Host ''
        Write-Host 'Application token for the annotation GUI' -ForegroundColor Cyan
        $token = New-AnnotationGuiToken -ApiDir $apiDir
    }

    Write-Host ''
    Write-Host 'Ready. Start the API with:' -ForegroundColor Green
    Write-Host '    cd MARP_API'
    Write-Host '    npm run dev'
    Write-Host ''
    if ($loginReady) {
        Write-Host "  Log in at http://localhost:3000 as '$AdminUsername'." -ForegroundColor DarkGray
    } else {
        Write-Host '  No login yet. Create one with:' -ForegroundColor Yellow
        Write-Host "       cd MARP_API; node scripts/set-user-password.js --name ""$AdminName"" --username $AdminUsername" -ForegroundColor DarkGray
    }
    if ($token) {
        Write-Host '  The annotation GUI has its token; build and run it.' -ForegroundColor DarkGray
    }
    Write-Host '  Jellyfin settings in .env are only needed for routes that resolve media.' -ForegroundColor DarkGray
}

<#
.SYNOPSIS
    Create or update MARP_API's .env for the local database.

.OUTPUTS
    System.Boolean. False when there was nothing to write to.
#>
function Set-ApiEnvironment {
    param([Parameter(Mandatory)][string]$ApiDir)

    $envPath = Join-Path $ApiDir '.env'
    $examplePath = Join-Path $ApiDir '.env.example'

    if (-not (Test-Path -LiteralPath $envPath)) {
        if (-not (Test-Path -LiteralPath $examplePath)) {
            Write-Fail 'No .env and no .env.example to start from.'
            return $false
        }
        Copy-Item -LiteralPath $examplePath -Destination $envPath
        Write-Pass 'created from .env.example'
    } else {
        # A copy is kept before anything changes. Only the database keys are
        # rewritten, but somebody's configuration file is not the place to rely
        # on that being bug-free.
        Copy-Item -LiteralPath $envPath -Destination "$envPath.bak" -Force
        Write-Pass 'existing .env backed up to .env.bak'
    }

    foreach ($pair in @(
        @('DB_HOST', '127.0.0.1'), @('DB_PORT', "$Port"), @('DB_NAME', 'mare_v1'),
        @('DB_USER', 'marp_user'), @('DB_PASSWORD', $Password), @('DB_DIALECT', 'postgres')
    )) {
        Set-EnvValue -Path $envPath -Key $pair[0] -Value $pair[1]
    }
    Write-Pass 'DB_* settings point at the local database'

    # Only filled when missing or still the template's placeholder: an existing
    # secret is somebody's session state, and replacing it logs everyone out.
    $secret = Get-EnvValue -Path $envPath -Key 'AUTH_SESSION_SECRET'
    if ([string]::IsNullOrWhiteSpace($secret) -or $secret -like 'replace-with*') {
        $bytes = New-Object byte[] 48
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        Set-EnvValue -Path $envPath -Key 'AUTH_SESSION_SECRET' -Value ([Convert]::ToBase64String($bytes))
        Write-Pass 'AUTH_SESSION_SECRET generated'
    } else {
        Write-Pass 'AUTH_SESSION_SECRET already set, left alone'
    }

    $admin = Get-EnvValue -Path $envPath -Key 'BOOTSTRAP_ADMIN_NAME'
    if ([string]::IsNullOrWhiteSpace($admin) -or $admin -like 'replace-with*') {
        Set-EnvValue -Path $envPath -Key 'BOOTSTRAP_ADMIN_NAME' -Value $AdminName
        Write-Pass "BOOTSTRAP_ADMIN_NAME set to $AdminName"
    } else {
        Write-Pass "BOOTSTRAP_ADMIN_NAME already set to $admin"
    }

    return $true
}

<#
.SYNOPSIS
    Give the bootstrap administrator a password, so somebody can log in.

.DESCRIPTION
    The bootstrap migration grants the first account every right and sets no
    credential, on purpose -- a password hash in a committed migration is a
    credential in source control. Without this step the only administrator on a
    new database holds every permission and cannot reach any of them.

.OUTPUTS
    System.Boolean. True when a login now exists.
#>
function Set-FirstAdministrator {
    param([Parameter(Mandatory)][string]$ApiDir)

    $passwordScript = Join-Path $ApiDir 'scripts\set-user-password.js'
    if (-not (Test-Path -LiteralPath $passwordScript)) {
        Write-Warn 'MARP_API has no scripts/set-user-password.js on this branch.'
        return $false
    }

    $password = $AdminPassword
    if ([string]::IsNullOrWhiteSpace($password)) {
        # Read as a secure string so it is not echoed and does not reach shell
        # history. Unattended runs should pass -AdminPassword instead.
        try {
            $secure = Read-Host -Prompt "  Password for '$AdminUsername'" -AsSecureString
            $password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
        } catch {
            Write-Warn 'Cannot prompt for a password here. Pass -AdminPassword, or set one later.'
            return $false
        }
    }

    if ([string]::IsNullOrWhiteSpace($password)) {
        Write-Warn 'No password given, so no login was created.'
        return $false
    }

    Push-Location $ApiDir
    try {
        Invoke-Native 'node' @('scripts/set-user-password.js',
                               '--name', $AdminName, '--username', $AdminUsername,
                               '--password', $password)
    } finally { Pop-Location }

    if ($script:LastNativeExit -ne 0) {
        Write-Warn 'Could not set the password. Run set-user-password.js --list to see the accounts.'
        return $false
    }
    return $true
}

<#
.SYNOPSIS
    Create an application token and hand it to the annotation GUI.

.DESCRIPTION
    Every route requires a permission, so the GUI cannot call anything without
    a token -- and it reads one from a file in its own data directory rather
    than being configured at runtime. The raw token is shown exactly once by
    the script that mints it, so it is captured here and written straight to
    that file, which is git-ignored in the GUI's repository.

.OUTPUTS
    System.String. The token, or $null when none was created.
#>
function New-AnnotationGuiToken {
    param([Parameter(Mandatory)][string]$ApiDir)

    $tokenScript = Join-Path $ApiDir 'scripts\create-application-token.js'
    if (-not (Test-Path -LiteralPath $tokenScript)) {
        Write-Warn 'MARP_API has no scripts/create-application-token.js on this branch.'
        return $null
    }

    Push-Location $ApiDir
    try {
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $output = & node 'scripts/create-application-token.js' '--app' 'MARE Video Processing GUI' '--preset' 'annotation-gui' 2>&1
            $exit = $LASTEXITCODE
        } finally { $ErrorActionPreference = $previous }
    } finally { Pop-Location }

    if ($exit -ne 0) {
        Write-Warn 'Could not create an application token.'
        return $null
    }

    # The minting script frames the raw token between two rules and says it is
    # not recoverable afterwards, so it is read from between them rather than
    # asked for a second time.
    $lines = @($output | ForEach-Object { "$_" })
    $token = $null
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^-+ the token') {
            $token = $lines[$i + 1].Trim()
            break
        }
    }

    if (-not $token) {
        Write-Warn 'A token was created but could not be read from the output.'
        Write-Warn 'Run create-application-token.js by hand to get one.'
        return $null
    }

    Write-Pass 'token created'

    $guiData = Join-Path $RepoRoot 'VIDEO_PROCESSING_GUI\MAREGUI_PROOFofCONCEPT\data'
    if (-not (Test-Path -LiteralPath $guiData)) {
        Write-Warn 'VIDEO_PROCESSING_GUI is not cloned, so the token was not delivered.'
        Write-Host ''
        Write-Host "  $token"
        Write-Host ''
        return $token
    }

    # No trailing newline: the GUI reads the file's contents as the token.
    $tokenFile = Join-Path $guiData 'MARP_API_TOKEN.txt'
    [IO.File]::WriteAllText($tokenFile, $token)
    Write-Pass 'written to VIDEO_PROCESSING_GUI\MAREGUI_PROOFofCONCEPT\data\MARP_API_TOKEN.txt'

    # The address file is tracked in that repository, so it is checked and
    # reported rather than rewritten: changing it would show up as a
    # modification somebody then has to explain.
    $addressFile = Join-Path $guiData 'API_IP_ADDRESS.txt'
    if (Test-Path -LiteralPath $addressFile) {
        $current = (Get-Content -LiteralPath $addressFile -Raw).Trim()
        if ($current -eq 'http://localhost:3000') {
            Write-Pass "API address already $current"
        } else {
            Write-Warn "API_IP_ADDRESS.txt says $current, not http://localhost:3000."
            Write-Warn 'That file is tracked in VIDEO_PROCESSING_GUI, so it is left alone.'
        }
    }

    return $token
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
        Write-Host 'Every repository is cloned.' -ForegroundColor Green
        Show-NextSteps
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
        # Asking about a path inside the directory rather than about the
        # directory itself. A trailing slash makes check-ignore report a false
        # positive for a directory that no rule covers at all, and a bare name
        # fails to match a directory-only rule when the directory is not yet on
        # disk. "<dir>/.git" is right in both cases, and every one of these
        # directories is a Git repository, so it is the honest thing to ask
        # about.
        & git -C $RepoRoot check-ignore --quiet -- "$($entry.directory)/.git" 2>&1 | Out-Null
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
        $legacyPath = Join-Path $RepoRoot $legacy
        if (-not (Test-Path -LiteralPath $legacyPath)) { continue }
        $anyLegacy = $true
        $current = $LegacyDirectories[$legacy]

        # An empty shell left behind by a part-finished rename is a different
        # problem from a directory that still holds the repository, and telling
        # someone to rename a directory they have already renamed would send
        # them looking for work that is done.
        $isEmpty = -not (Get-ChildItem -LiteralPath $legacyPath -Force -ErrorAction SilentlyContinue)
        if ($isEmpty -and (Test-Path -LiteralPath (Join-Path $RepoRoot "$current\.git"))) {
            Write-Warn "$legacy/ is an empty leftover from the rename to $current/; delete it (something may still hold it open)"
        } else {
            Write-Warn "$legacy/ is still here; it was renamed to $current/ -- rename it so the workspace file and the registry find it"
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
        Show-NextSteps
    } else {
        Write-Host "$($script:Failures) problem(s) found." -ForegroundColor Red
    }
}

# ---------------------------------------------------------------------------

# The database is its own script: it is long, it is about PostgreSQL rather
# than about repositories, and keeping it separate means neither file has to be
# read to understand the other. `marp db <subcommand>` is the only entry point.
if ($Command -eq 'db') {
    $dbScript = Join-Path $PSScriptRoot 'db.ps1'
    if (-not (Test-Path -LiteralPath $dbScript)) { throw "Missing $dbScript" }

    $arguments = @{}
    if ($Component) { $arguments['Command'] = $Component }
    if ($PSBoundParameters.ContainsKey('Port')) { $arguments['Port'] = $Port }
    if ($PSBoundParameters.ContainsKey('Password')) { $arguments['Password'] = $Password }

    & $dbScript @arguments
    exit $LASTEXITCODE
}

$entries = Read-Registry

switch ($Command) {
    'setup'  { Invoke-Setup  $entries }
    'clone'  { Invoke-Clone  $entries }
    'list'   { Invoke-List   $entries }
    'status' { Invoke-Status $entries }
    'pull'   { Invoke-Pull   $entries }
    'doctor' { Invoke-Doctor $entries }
}

if ($script:Failures -gt 0) { exit 1 } else { exit 0 }
