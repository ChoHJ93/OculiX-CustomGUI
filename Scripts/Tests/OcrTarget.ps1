Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# 한글 글자 인식(OCR) 검증용 창.
# 라벨마다 화면 좌표와 기대 문자열을 파일로 내보내고, 클릭을 기록한다.
# 매크로가 "설정" 을 찾아 클릭했을 때 정말 그 라벨이 눌렸는지 대조하기 위한 것이다.

$STATE = "D:\Programming\Oculix-Automation\Logs\ocr_target.txt"

$form = New-Object System.Windows.Forms.Form
$form.Text = "OCR Test Target"
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedSingle
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
# 영문 대상 창(TestTarget.ps1, 208,231 800x560)과 겹치지 않도록 오른쪽에 둔다.
# 겹치면 위 창만 읽혀서 측정이 조용히 틀어진다.
$form.Location = New-Object System.Drawing.Point(1240, 250)
$form.ClientSize = New-Object System.Drawing.Size(560, 340)
$form.BackColor = [System.Drawing.Color]::White
$form.TopMost = $true
$form.MaximizeBox = $false

$items = @(
  @("kr1", "설정 열기", 20, 20, 20),
  @("kr2", "확인", 20, 80, 20),
  @("kr3", "다음 단계로 진행", 20, 140, 16),
  @("en1", "Open Settings", 20, 200, 20),
  @("mix", "Hyper-V 관리자", 20, 260, 18)
)

$script:clicks = 0
$script:lastClick = ""
$script:hits = @{}

$labels = @{}
foreach ($i in $items) {
  $key = $i[0]
  $script:hits[$key] = 0
  $l = New-Object System.Windows.Forms.Label
  $l.Text = $i[1]
  $l.Font = New-Object System.Drawing.Font("맑은 고딕", $i[4])
  $l.ForeColor = [System.Drawing.Color]::Black
  $l.BackColor = [System.Drawing.Color]::White
  $l.Location = New-Object System.Drawing.Point($i[2], $i[3])
  $l.AutoSize = $true
  $l.Tag = $key
  $l.Add_Click({
    $k = $this.Tag
    $script:clicks++
    $script:lastClick = $k
    $script:hits[$k] = $script:hits[$k] + 1
    Write-State
  })
  $form.Controls.Add($l)
  $labels[$key] = $l
}

function Write-State {
  $lines = New-Object System.Collections.Generic.List[string]
  $p = $form.PointToScreen([System.Drawing.Point]::Empty)
  $lines.Add(("rect.form={0},{1},{2},{3}" -f $p.X, $p.Y, $form.ClientSize.Width, $form.ClientSize.Height))
  foreach ($k in $labels.Keys) {
    $c = $labels[$k]
    $q = $c.PointToScreen([System.Drawing.Point]::Empty)
    $lines.Add(("rect.{0}={1},{2},{3},{4}" -f $k, $q.X, $q.Y, $c.Size.Width, $c.Size.Height))
    $lines.Add(("text.{0}={1}" -f $k, $c.Text))
    $lines.Add(("hits.{0}={1}" -f $k, $script:hits[$k]))
  }
  $lines.Add(("clicks={0}" -f $script:clicks))
  $lines.Add(("lastClick={0}" -f $script:lastClick))
  [System.IO.File]::WriteAllLines($STATE, $lines, [System.Text.Encoding]::UTF8)
}

# 폼 바탕을 눌렀을 때는 어느 라벨도 아님을 남긴다. 빗나간 클릭을 알아채기 위한 것이다.
$form.Add_Click({
  $script:clicks++
  $script:lastClick = "form"
  Write-State
})

$form.Add_Shown({ $form.Activate(); Write-State })
$form.Add_LocationChanged({ Write-State })
[System.Windows.Forms.Application]::Run($form)
