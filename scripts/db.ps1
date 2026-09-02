<#
.SYNOPSIS
    Provision and run the MARP PostgreSQL database. Invoked as `marp db <command>`.

.DESCRIPTION
    marp-api cannot run without a PostgreSQL database, and nothing else in the
    workspace provided one -- the development database was a hand-built server
    on a virtual machine, which a second machine cannot reproduce
    automatically. This script closes that gap.

    It downloads a self-contained PostgreSQL, creates a database cluster inside
    this workspace, and starts it. No installer, no administrator rights, no
    virtual machine, no container runtime. These are the official PostgreSQL
    binaries as published for Windows, in their plain archive form rather than
    wrapped in an installer: the same server, simply not registered with the
    operating system.

    Nothing lands outside the workspace. The binaries and the database both
    live under `.postgres/`, which is git-ignored, so deleting this workspace
    leaves nothing behind.

    The schema is not this script's to own. It belongs to marp-api, which
    carries the baseline and the migrations, so `up` finishes by running
    marp-api's own two commands against the new database. If marp-api is not
    cloned or not installed, it stops and prints the commands instead of
    guessing -- a running database and honest instructions beat a silent
    half-finished one.

    Commands:

      up        fetch, start, create the database, and load the schema.
      down      stop the server. The database is kept.
      status    what exists and what is running.
      env       the DB_* settings marp-api needs.
      destroy   stop the server and delete the database.

.PARAMETER Command
    One of the commands above. Defaults to status, which changes nothing.

.PARAMETER Port
    TCP port. Defaults to 5432, PostgreSQL's own port, because tools and
    documentation assume it. If something is already listening there this
    script stops and says so rather than quietly choosing another port and
    leaving your .env disagreeing with reality -- pass -Port to place it
    elsewhere deliberately.

.PARAMETER Password
    Password for the database role. Defaults to a well-known development
    value. The server listens only on 127.0.0.1.

.NOTES
    Author: Isaac Travers
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('up', 'down', 'status', 'env', 'destroy')]
    [string]$Command = 'status',

    [int]$Port = 5432,

    [string]$Password = 'marp_dev_password'
)

$ErrorActionPreference = 'Stop'

$RepoRoot    = Split-Path -Parent $PSScriptRoot
$PostgresDir = Join-Path $RepoRoot '.postgres'
$BinDir      = Join-Path $PostgresDir 'pgsql\bin'
$DataDir     = Join-Path $PostgresDir 'data'
$LogFile     = Join-Path $PostgresDir 'server.log'

# Pinned rather than tracking latest, so "it worked last week" stays
# traceable. 18.6 matches the development server, removing one difference
# between a machine set up by this script and the one that has been in use.
$PostgresVersion = '18.6-1'
$PostgresUrl     = "https://get.enterprisedb.com/postgresql/postgresql-$PostgresVersion-windows-x64-binaries.zip"

$Role     = 'marp_user'
$Database = 'mare_v1'
$DbHost   = '127.0.0.1'

# Where marp-api is expected, and the two commands that put its schema into a
# database. Both come from that repository; this script only calls them.
$ApiDir = Join-Path $RepoRoot 'MARP_API'

function Write-Step { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "    $Message" -ForegroundColor DarkGray }
function Write-Warn { param([string]$Message) Write-Host "    $Message" -ForegroundColor Yellow }

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

    The exit code is left in $script:LastNativeExit rather than returned. A
    function that returns it would hand the caller the command's entire stdout
    with the code appended -- an array, on which `-ne 0` filters instead of
    comparing, so every check would pass or fail for the wrong reason.

.OUTPUTS
    None. The command's own output goes straight to the host.
#>
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$Command,
        [string[]]$Arguments = @()
    )

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Command @Arguments
        $script:LastNativeExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Test-Fetched     { Test-Path -LiteralPath (Join-Path $BinDir 'postgres.exe') }
function Test-Initialised { Test-Path -LiteralPath (Join-Path $DataDir 'PG_VERSION') }

<#
.SYNOPSIS
    Run one of the bundled PostgreSQL executables.

.DESCRIPTION
    Every call goes through here so the password is set for the child process
    only. Putting PGPASSWORD in the ambient environment would leak it to
    everything else launched from the same shell.
#>
function Invoke-Pg {
    param([Parameter(Mandatory)][string]$Tool, [string[]]$Arguments = @())

    $exe = Join-Path $BinDir "$Tool.exe"
    if (-not (Test-Path -LiteralPath $exe)) { throw "$Tool is missing from .postgres. Run: marp db up" }

    # ErrorActionPreference is relaxed for the call: with 'Stop', anything
    # psql writes to stderr becomes a terminating error regardless of its exit
    # code, so a query that merely reports a missing relation took the whole
    # script down instead of returning a value the caller could handle.
    $previousPassword = $env:PGPASSWORD
    $previousAction = $ErrorActionPreference
    $env:PGPASSWORD = $Password
    $ErrorActionPreference = 'Continue'
    try { & $exe @Arguments } finally {
        $env:PGPASSWORD = $previousPassword
        $ErrorActionPreference = $previousAction
    }
}

function Test-Running {
    if (-not (Test-Initialised)) { return $false }
    & (Join-Path $BinDir 'pg_ctl.exe') -D $DataDir status 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

<#
.SYNOPSIS
    Identify whatever is already listening on the chosen port.

.DESCRIPTION
    Returned as text for a message rather than as a decision. A port in use is
    not always a problem -- it may be this script's own server from a previous
    session -- so the caller decides what it means.
#>
function Get-PortHolder {
    try {
        $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
        $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        if ($process) { return "$($process.ProcessName) (PID $($process.Id))" }
        return "PID $($connection.OwningProcess)"
    } catch {
        return $null
    }
}

# ---------------------------------------------------------------------------

<#
.SYNOPSIS
    Download a file, reporting progress as it goes.

.DESCRIPTION
    Written by hand rather than using Invoke-WebRequest because neither of its
    modes is acceptable here. With progress rendering on, a 330 MB download in
    Windows PowerShell is dramatically slower; with it suppressed, the command
    prints nothing at all for several minutes. A download that looks hung gets
    killed -- which is exactly what happened -- so the bytes are copied here in
    chunks and a line is printed every 25 MB.

    Downloads to a temporary name and renames on success, so an interrupted
    download cannot be mistaken for a complete archive on the next run.
#>
function Get-Download {
    param(
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][string]$Destination
    )

    $partial = "$Destination.partial"
    $request = [System.Net.HttpWebRequest]::Create($Url)
    $request.UserAgent = 'marp-db'
    $response = $request.GetResponse()

    $total = $response.ContentLength
    $totalText = if ($total -gt 0) { '{0:N0} MB' -f ($total / 1MB) } else { 'unknown size' }

    $input = $response.GetResponseStream()
    $output = [System.IO.File]::Create($partial)
    $buffer = New-Object byte[] (1MB)
    $done = 0L
    $lastReport = 0L

    try {
        while (($read = $input.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $output.Write($buffer, 0, $read)
            $done += $read

            if (($done - $lastReport) -ge 25MB) {
                $lastReport = $done
                if ($total -gt 0) {
                    Write-Ok ('{0:N0} MB of {1} ({2:N0}%)' -f ($done / 1MB), $totalText, (100 * $done / $total))
                } else {
                    Write-Ok ('{0:N0} MB' -f ($done / 1MB))
                }
            }
        }
    } finally {
        $output.Dispose()
        $input.Dispose()
        $response.Dispose()
    }

    Move-Item -LiteralPath $partial -Destination $Destination -Force
    Write-Ok ('{0:N0} MB downloaded' -f ($done / 1MB))
}

function Invoke-Fetch {
    if (Test-Fetched) { Write-Ok "PostgreSQL $PostgresVersion already in .postgres/"; return }

    New-Item -ItemType Directory -Path $PostgresDir -Force | Out-Null
    $archive = Join-Path $PostgresDir "postgresql-$PostgresVersion.zip"

    if (-not (Test-Path -LiteralPath $archive)) {
        Write-Step "Downloading PostgreSQL $PostgresVersion -- about 330 MB, once"
        Get-Download $PostgresUrl $archive
    } else {
        Write-Ok 'archive already downloaded, reusing it'
    }

    Write-Step 'Unpacking -- around a minute, expands to about 920 MB'
    Expand-Archive -LiteralPath $archive -DestinationPath $PostgresDir -Force
    if (-not (Test-Fetched)) { throw 'Archive did not contain pgsql\bin\postgres.exe' }

    Remove-Item -LiteralPath $archive -Force
    Write-Ok ((& (Join-Path $BinDir 'postgres.exe') --version) -join '')
}

<#
.SYNOPSIS
    Create the database cluster.

.DESCRIPTION
    The password reaches initdb through a file, not a command-line argument:
    arguments are visible to anything that can list processes. The file is
    removed immediately afterwards.
#>
function Invoke-Init {
    if (Test-Initialised) { Write-Ok '.postgres/data already initialised'; return }

    Invoke-Fetch
    Write-Step 'Creating the database cluster -- around a minute'

    $passwordFile = Join-Path $PostgresDir '.initdb-password'
    # -NoNewline, or the trailing newline becomes part of the password.
    Set-Content -LiteralPath $passwordFile -Value $Password -NoNewline -Encoding ascii
    try {
        # --no-sync skips flushing the new cluster to disk, which is most of
        # initdb's runtime on Windows. The risk it accepts is losing the
        # cluster if the machine dies during these few seconds -- and the
        # answer to that is `marp db up` again. Not a trade worth making for a
        # database holding real records; entirely worth it for this one.
        Invoke-Pg initdb @('-D', $DataDir, '-U', $Role, '--auth=scram-sha-256',
                           "--pwfile=$passwordFile", '--encoding=UTF8', '--no-sync') | Out-Null
    } finally {
        Remove-Item -LiteralPath $passwordFile -Force -ErrorAction SilentlyContinue
    }
    Write-Ok "cluster created, role '$Role'"
}

function Invoke-Start {
    Invoke-Init
    if (Test-Running) { Write-Ok "already running on port $Port"; return }

    # Checked before starting rather than after failing, so the message names
    # the real problem instead of leaving a startup error in a log file.
    $holder = Get-PortHolder
    if ($holder) {
        throw "Port $Port is already in use by $holder. Stop it, or place this database elsewhere with: marp db up -Port 5433"
    }

    Write-Step "Starting PostgreSQL on ${DbHost}:$Port"

    # Starting a server from PowerShell is a nest of ways to wait forever, and
    # two of them were hit before landing here.
    #
    # The call operator reads a native command's stdout to end-of-file. pg_ctl
    # exits in a second, but the postgres server it spawns inherits that pipe
    # and holds it open for as long as it runs -- so PowerShell blocks on a
    # command that finished, with a working database behind it.
    #
    # Start-Process -Wait is worse: it waits for the process *and all its
    # descendants*, which is precisely the server we intend to leave running.
    #
    # So: -W tells pg_ctl not to wait for readiness, Start-Process without
    # -Wait leaves the tree alone, WaitForExit waits for pg_ctl and nothing
    # below it, and readiness is then established by asking -- which is the
    # only claim worth making anyway.
    $startupLog = Join-Path $PostgresDir 'pg_ctl-start.log'
    $previous = $env:PGPASSWORD
    $env:PGPASSWORD = $Password
    try {
        $process = Start-Process -FilePath (Join-Path $BinDir 'pg_ctl.exe') `
            -ArgumentList @('-D', "`"$DataDir`"", '-l', "`"$LogFile`"",
                            '-o', "`"-p $Port -c listen_addresses=127.0.0.1`"",
                            '-W', 'start') `
            -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $startupLog -RedirectStandardError "$startupLog.err"

        if (-not $process.WaitForExit(30000)) {
            try { $process.Kill() } catch { }
            throw "pg_ctl did not exit within 30s. See $startupLog"
        }
    } finally {
        $env:PGPASSWORD = $previous
    }

    # Readiness is polled rather than assumed: -W means pg_ctl returns before
    # the server is accepting connections.
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if (Test-Running) { break }
        Start-Sleep -Milliseconds 400
    }

    if (-not (Test-Running)) {
        Write-Warn "pg_ctl exited with $($process.ExitCode)"
        foreach ($log in @($LogFile, $startupLog, "$startupLog.err")) {
            if (Test-Path -LiteralPath $log) {
                Get-Content -LiteralPath $log -Tail 4 -ErrorAction SilentlyContinue | ForEach-Object { Write-Warn $_ }
            }
        }
        throw "Server did not start. See $LogFile"
    }
    Write-Ok 'running'
}

function Invoke-Stop {
    if (-not (Test-Initialised)) { Write-Ok 'nothing to stop'; return }
    if (-not (Test-Running))     { Write-Ok 'not running'; return }

    Write-Step 'Stopping PostgreSQL'
    Invoke-Pg pg_ctl @('-D', $DataDir, '-m', 'fast', 'stop') | Out-Null
    Write-Ok 'stopped'
}

<#
.SYNOPSIS
    Record whether the database is empty, before anything touches it.

.DESCRIPTION
    Read once, up front, because it decides whether the baseline applies and
    the answer changes the moment it is used.
#>
function Test-DatabaseEmpty {
    $tables = (Invoke-Pg psql @('-h', $DbHost, '-p', "$Port", '-U', $Role, '-d', $Database,
                                '-tAc', "select count(*) from information_schema.tables where table_schema = 'public'") 2>$null) -join ''
    if ($LASTEXITCODE -ne 0 -or -not $tables) { return $true }
    return ([int]$tables -eq 0)
}

function New-MarpDatabase {
    $exists = Invoke-Pg psql @('-h', $DbHost, '-p', "$Port", '-U', $Role, '-d', 'postgres',
                               '-tAc', "select 1 from pg_database where datname = '$Database'")
    if ($exists -match '1') { Write-Ok "database $Database already exists"; return }

    Write-Step "Creating database $Database"
    Invoke-Pg createdb @('-h', $DbHost, '-p', "$Port", '-U', $Role, $Database) | Out-Null
}

<#
.SYNOPSIS
    Have marp-api put its schema into the new database.

.DESCRIPTION
    The schema belongs to marp-api: it holds the baseline and every migration.
    So rather than keep a second copy here -- which would drift the first time
    somebody adds a migration -- this runs marp-api's own commands.

    Returns false rather than throwing when marp-api cannot be driven. A
    database that exists but is empty is a perfectly good outcome as long as
    the caller is told plainly what is left to do; failing loudly would suggest
    the provisioning went wrong when it did not.

.OUTPUTS
    System.Boolean. True when the schema was loaded here.
#>
function Invoke-LoadSchema {
    if (-not (Test-Path -LiteralPath (Join-Path $ApiDir 'package.json'))) {
        Write-Warn 'MARP_API is not cloned, so the schema was not loaded.'
        return $false
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ApiDir 'node_modules'))) {
        Write-Warn 'MARP_API has no node_modules, so the schema was not loaded.'
        return $false
    }

    # Checked by name rather than discovered by failure. Node is installed
    # through nvm-windows here, and a shell opened before that installation
    # does not have the symlink on PATH -- so "node is not recognised" is a
    # routine state in this workspace, not a broken machine. Blaming
    # init-database.js for it would send someone debugging the wrong thing.
    # The script being called has to exist. It lives on marp-api's develop
    # branch, and cloning GitHub's default put workspaces on master -- a year
    # behind, without this file. That surfaced as a Node module-not-found stack
    # trace, which says nothing about the actual problem, so the branch is
    # named instead.
    $initScript = Join-Path $ApiDir 'scripts\init-database.js'
    if (-not (Test-Path -LiteralPath $initScript)) {
        $branch = (& git -C $ApiDir rev-parse --abbrev-ref HEAD 2>$null) -join ''
        Write-Warn "MARP_API has no scripts/init-database.js, so the schema was not loaded."
        Write-Warn "It is on branch '$branch', which does not carry it. The registry expects develop:"
        Write-Warn '    cd MARP_API; git checkout develop; npm install'
        Write-Warn 'If checkout refuses because package-lock.json changed, that change is'
        Write-Warn 'npm''s own: git checkout -- package-lock.json first.'
        return $false
    }

    foreach ($tool in @('node', 'npx')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            Write-Warn "$tool is not on PATH, so the schema was not loaded."
            Write-Warn 'Node is installed via nvm-windows; a shell opened before that needs'
            Write-Warn 'C:/nvm4w/nodejs prepended to PATH, or just open a new terminal.'
            return $false
        }
    }

    # Passed as real environment variables rather than written into
    # MARP_API/.env: dotenv does not override variables already set, so these
    # win for these two commands only and that repository's own configuration
    # is left exactly as the developer wrote it.
    $environment = @{
        DB_HOST = $DbHost; DB_PORT = "$Port"; DB_NAME = $Database
        DB_USER = $Role;   DB_PASSWORD = $Password; DB_DIALECT = 'postgres'
    }
    $saved = @{}
    foreach ($key in $environment.Keys) {
        $saved[$key] = [Environment]::GetEnvironmentVariable($key)
        Set-Item -Path "env:$key" -Value $environment[$key]
    }

    $previousLocation = Get-Location
    try {
        Set-Location -LiteralPath $ApiDir

        # The baseline is only for an empty database -- init-database.js
        # refuses a populated one, and rightly so. On a second `up` that
        # refusal is the correct answer, not a failure, so the emptiness is
        # checked here rather than inferred from an exit code. Migrating,
        # by contrast, is always right: it is a no-op when there is nothing
        # pending.
        if ($script:DatabaseIsEmpty) {
            Write-Step 'Loading the baseline schema (MARP_API)'
            Invoke-Native 'node' @('scripts/init-database.js')
            if ($script:LastNativeExit -ne 0) {
                Write-Warn 'init-database.js did not succeed'; return $false
            }
        } else {
            Write-Ok 'schema already present, so the baseline was not reapplied'
        }

        Write-Step 'Applying migrations (MARP_API)'
        Invoke-Native 'npx' @('sequelize-cli', 'db:migrate')
        if ($script:LastNativeExit -ne 0) {
            Write-Warn 'db:migrate did not succeed'; return $false
        }

        return $true
    } finally {
        Set-Location $previousLocation
        foreach ($key in $environment.Keys) {
            if ($null -eq $saved[$key]) { Remove-Item -Path "env:$key" -ErrorAction SilentlyContinue }
            else { Set-Item -Path "env:$key" -Value $saved[$key] }
        }
    }
}

function Invoke-Up {
    Invoke-Start
    New-MarpDatabase
    $script:DatabaseIsEmpty = Test-DatabaseEmpty
    $loaded = Invoke-LoadSchema

    Write-Host ''
    if ($loaded) {
        Write-Host 'Database ready.' -ForegroundColor Green
        Invoke-Env
    } else {
        Write-Host 'Database is running, but the schema is not loaded.' -ForegroundColor Yellow
        Write-Host ''
        Write-Host 'Finish it in the MARP_API checkout:' -ForegroundColor Cyan
        Write-Host '    cd MARP_API'
        Write-Host '    npm install                      # if you have not already'
        Write-Host '    node scripts/init-database.js'
        Write-Host '    npx sequelize-cli db:migrate'
        Invoke-Env
    }
}

function Invoke-Status {
    Write-Step 'MARP database'

    if (-not (Test-Fetched))     { Write-Warn 'PostgreSQL not downloaded (run: marp db up)'; return }
    Write-Ok ((& (Join-Path $BinDir 'postgres.exe') --version) -join '')

    if (-not (Test-Initialised)) { Write-Warn 'cluster not created (run: marp db up)'; return }

    if (-not (Test-Running)) {
        Write-Warn 'not running (run: marp db up)'
        $holder = Get-PortHolder
        if ($holder) { Write-Warn "note: something else is on port $Port -- $holder" }
        return
    }

    Write-Ok "running on ${DbHost}:$Port"

    # SequelizeMeta needs its quotes: unquoted identifiers are folded to
    # lower case by PostgreSQL, and there is no `sequelizemeta`. The quotes are
    # backslash-escaped because PowerShell does not escape embedded quotes when
    # building a native process's command line -- they were being stripped, so
    # this query failed against a database that was perfectly healthy.
    $summarySql = 'select (select count(*) from information_schema.tables where table_schema=' +
        "'public'" + ' and table_type=' + "'BASE TABLE'" + ') || ' + "' tables, '" +
        ' || (select count(*) from information_schema.tables where table_schema=' + "'public'" +
        ' and table_type=' + "'VIEW'" + ') || ' + "' views, '" +
        ' || (select count(*) from \"SequelizeMeta\") || ' + "' migrations applied'"

    $summary = (Invoke-Pg psql @('-h', $DbHost, '-p', "$Port", '-U', $Role, '-d', $Database,
                                 '-tAc', $summarySql) 2>$null) -join ''

    if ($LASTEXITCODE -eq 0 -and $summary) { Write-Ok "$Database`: $summary" }
    else { Write-Warn "$Database has no schema yet -- see: marp db up" }
}

<#
.SYNOPSIS
    Print the settings marp-api needs.

.DESCRIPTION
    Printed, not written. MARP_API/.env also holds Jellyfin credentials, a
    session secret and reporting connection details; rewriting somebody's
    configuration file to save them a copy and paste is a poor trade.
#>
function Invoke-Env {
    Write-Host ''
    Write-Host 'Set these in MARP_API\.env :' -ForegroundColor Cyan
    Write-Host ''
    Write-Host "DB_HOST=$DbHost"
    Write-Host "DB_PORT=$Port"
    Write-Host "DB_NAME=$Database"
    Write-Host "DB_USER=$Role"
    Write-Host "DB_PASSWORD=$Password"
    Write-Host 'DB_DIALECT=postgres'
    Write-Host ''
}

function Invoke-Destroy {
    Invoke-Stop
    if (-not (Test-Path -LiteralPath $DataDir)) { Write-Ok 'no database to delete'; return }

    Write-Step 'Deleting the database'
    Remove-Item -LiteralPath $DataDir -Recurse -Force
    Remove-Item -LiteralPath $LogFile -Force -ErrorAction SilentlyContinue
    Write-Ok 'deleted. The PostgreSQL binaries are kept, so `up` will not download again.'
}

# ---------------------------------------------------------------------------

switch ($Command) {
    'up'      { Invoke-Up }
    'down'    { Invoke-Stop }
    'status'  { Invoke-Status }
    'env'     { Invoke-Env }
    'destroy' { Invoke-Destroy }
}
