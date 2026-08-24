# TestTarget.ps1 - deterministic WinForms window used as the OculiX automation target.
#
# Why a dedicated window instead of Notepad: the user has real unsaved Notepad
# documents open. Driving real mouse/keyboard against Notepad risks typing into
# their work. This window is disposable and reports ground truth to a state file,
# so every API can be verified against what the application actually received -
# not just against what the screen looks like.

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$StateFile = "D:\Programming\Oculix-Automation\Logs\target_state.txt"

$script:clicks     = 0
$script:keyDowns   = @()
$script:keyUps     = @()
$script:mouseDowns = 0
$script:mouseUps   = 0

$form = New-Object System.Windows.Forms.Form
$form.Text            = "OculiX Test Target"
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedSingle
$form.StartPosition   = [System.Windows.Forms.FormStartPosition]::Manual
$form.Location        = New-Object System.Drawing.Point(200, 200)
$form.ClientSize      = New-Object System.Drawing.Size(800, 560)
$form.BackColor       = [System.Drawing.Color]::White
$form.TopMost         = $true
$form.MaximizeBox     = $false

# Image-match target: high contrast, fixed glyphs, no animation.
$lblTarget = New-Object System.Windows.Forms.Label
$lblTarget.Text      = "OCULIX-TARGET"
$lblTarget.Font      = New-Object System.Drawing.Font("Consolas", 28, [System.Drawing.FontStyle]::Bold)
$lblTarget.ForeColor = [System.Drawing.Color]::Black
$lblTarget.BackColor = [System.Drawing.Color]::White
$lblTarget.Location  = New-Object System.Drawing.Point(40, 30)
$lblTarget.Size      = New-Object System.Drawing.Size(430, 55)
$lblTarget.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft

# Pixel-colour target: exact RGB before and after the click.
$pnlStatus = New-Object System.Windows.Forms.Panel
$pnlStatus.Location  = New-Object System.Drawing.Point(40, 110)
$pnlStatus.Size      = New-Object System.Drawing.Size(220, 120)
$pnlStatus.BackColor = [System.Drawing.Color]::FromArgb(200, 30, 30)   # red

# waitVanish target: visible until the button is clicked.
# It carries text on purpose - a flat colour block matches any similarly
# coloured area on screen, which makes waitVanish report false positives.
$pnlVanish = New-Object System.Windows.Forms.Panel
$pnlVanish.Location  = New-Object System.Drawing.Point(300, 110)
$pnlVanish.Size      = New-Object System.Drawing.Size(170, 120)
$pnlVanish.BackColor = [System.Drawing.Color]::FromArgb(20, 60, 200)   # blue

$lblVanish = New-Object System.Windows.Forms.Label
$lblVanish.Text      = "VANISH-7Q"
$lblVanish.Font      = New-Object System.Drawing.Font("Consolas", 14, [System.Drawing.FontStyle]::Bold)
$lblVanish.ForeColor = [System.Drawing.Color]::White
$lblVanish.BackColor = [System.Drawing.Color]::FromArgb(20, 60, 200)
$lblVanish.Location  = New-Object System.Drawing.Point(8, 45)
$lblVanish.Size      = New-Object System.Drawing.Size(155, 30)
$lblVanish.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$pnlVanish.Controls.Add($lblVanish)

$btnAction = New-Object System.Windows.Forms.Button
$btnAction.Text     = "CLICK ME"
$btnAction.Font     = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$btnAction.Location = New-Object System.Drawing.Point(40, 260)
$btnAction.Size     = New-Object System.Drawing.Size(220, 60)

$txtInput = New-Object System.Windows.Forms.TextBox
$txtInput.Font     = New-Object System.Drawing.Font("Consolas", 16)
$txtInput.Location = New-Object System.Drawing.Point(40, 350)
$txtInput.Size     = New-Object System.Drawing.Size(500, 32)

$lblEcho = New-Object System.Windows.Forms.Label
$lblEcho.Font      = New-Object System.Drawing.Font("Consolas", 14)
$lblEcho.ForeColor = [System.Drawing.Color]::FromArgb(0, 90, 0)
$lblEcho.Location  = New-Object System.Drawing.Point(40, 400)
$lblEcho.Size      = New-Object System.Drawing.Size(700, 30)

$form.Controls.AddRange(@($lblTarget, $pnlStatus, $pnlVanish, $btnAction, $txtInput, $lblEcho))

function Write-State {
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# OculiX test target state - rewritten on every event")
    $lines.Add("updated=" + (Get-Date -Format "HH:mm:ss.fff"))
    foreach ($pair in @(
        @("form",    $form),
        @("label",   $lblTarget),
        @("status",  $pnlStatus),
        @("vanish",  $pnlVanish),
        @("button",  $btnAction),
        @("textbox", $txtInput))) {
        $name = $pair[0]
        $c    = $pair[1]
        if ($name -eq "form") {
            $p = $form.PointToScreen([System.Drawing.Point]::Empty)
            $w = $form.ClientSize.Width
            $h = $form.ClientSize.Height
        } else {
            $p = $c.PointToScreen([System.Drawing.Point]::Empty)
            $w = $c.Size.Width
            $h = $c.Size.Height
        }
        $lines.Add(("rect.{0}={1},{2},{3},{4}" -f $name, $p.X, $p.Y, $w, $h))
    }
    $lines.Add("clicks="      + $script:clicks)
    $lines.Add("mouse_downs=" + $script:mouseDowns)
    $lines.Add("mouse_ups="   + $script:mouseUps)
    $lines.Add("key_downs="   + ($script:keyDowns   -join "|"))
    $lines.Add("key_ups="     + ($script:keyUps     -join "|"))
    $lines.Add("textbox="     + $txtInput.Text)
    $lines.Add("vanish_visible=" + $pnlVanish.Visible)
    $sc = $pnlStatus.BackColor
    $lines.Add(("status_rgb={0},{1},{2}" -f $sc.R, $sc.G, $sc.B))
    [System.IO.File]::WriteAllLines($StateFile, $lines, [System.Text.Encoding]::UTF8)
}

$btnAction.Add_Click({
    $script:clicks++
    $pnlStatus.BackColor = [System.Drawing.Color]::FromArgb(30, 160, 60)   # green
    $pnlVanish.Visible   = $false
    Write-State
})

# mouseDown / mouseUp are counted separately from Click so they can be proven
# independently of whether a full click was synthesised.
$pnlStatus.Add_MouseDown({ $script:mouseDowns++; Write-State })
$pnlStatus.Add_MouseUp({   $script:mouseUps++;   Write-State })

$txtInput.Add_KeyDown({ param($s, $e) $script:keyDowns += $e.KeyCode.ToString(); Write-State })
$txtInput.Add_KeyUp({   param($s, $e) $script:keyUps   += $e.KeyCode.ToString(); Write-State })
$txtInput.Add_TextChanged({ $lblEcho.Text = "echo: " + $txtInput.Text; Write-State })

$form.Add_Shown({ $form.Activate(); Write-State })

# 창이 움직이면 좌표를 즉시 다시 쓴다. 이게 없으면 상태 파일의 rect가 낡아서,
# 그 좌표를 믿고 클릭한 매크로가 엉뚱한 창을 누르게 된다.
$form.Add_LocationChanged({ Write-State })
$form.Add_SizeChanged({ Write-State })

[System.Windows.Forms.Application]::Run($form)
