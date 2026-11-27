# Microsoft Word 로 DOCX 를 직접 열어 변경 수·메모 수를 세고, 변경 표시(markup) 포함 PDF 로 내보낸다.
# Usage: powershell -File scripts/word_render_check.ps1 -Docx path.docx -Pdf out.pdf -Out out.txt [-Action none|reject|accept]
# -RedMarkup: 캡처하는 동안만 Word 변경 표시 색을 빨강(추가=밑줄, 삭제=취소선)으로 바꾸고 끝나면 원래 설정으로 되돌린다.
#   변경 표시 색은 문서가 아니라 보는 사람의 Word 설정(검토 > 변경 내용 추적 옵션)이 정한다 — 파일로 강제할 수 없다.
param([string]$Docx, [string]$Pdf, [string]$Out, [string]$Action = "none", [switch]$RedMarkup)
$ErrorActionPreference = 'Stop'
$tmp = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), [System.IO.Path]::GetRandomFileName() + ".docx")
Copy-Item -LiteralPath $Docx -Destination $tmp
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
$saved = $null
try {
  if ($RedMarkup) {
    $o = $w.Options
    $saved = @($o.InsertedTextColor, $o.InsertedTextMark, $o.DeletedTextColor, $o.DeletedTextMark)
    $o.InsertedTextColor = 6; $o.InsertedTextMark = 2; $o.DeletedTextColor = 6; $o.DeletedTextMark = 1
  }
  $d = $w.Documents.Open($tmp, $false, $false, $false)
  $revs = $d.Revisions.Count
  $cmts = $d.Comments.Count
  $authors = @()
  foreach ($r in $d.Revisions) { $authors += $r.Author }
  $cauth = @()
  foreach ($c in $d.Comments) { $cauth += $c.Author }
  if ($Action -eq 'reject') { $d.Revisions.RejectAll() }
  if ($Action -eq 'accept') { $d.Revisions.AcceptAll() }
  $text = $d.Content.Text
  if ($Pdf) {
    $w.ActiveWindow.View.RevisionsFilter.Markup = 2
    $w.ActiveWindow.View.ShowRevisionsAndComments = $true
    $d.ExportAsFixedFormat($Pdf, 17, $false, 0, 0, 1, 1, 7)
  }
  $d.Close(0)
  $lines = @("revisions=$revs", "comments=$cmts", "revision_authors=" + (($authors | Sort-Object -Unique) -join ','),
             "comment_authors=" + (($cauth | Sort-Object -Unique) -join ','), "---", $text)
  [System.IO.File]::WriteAllText($Out, ($lines -join "`n"), [System.Text.Encoding]::UTF8)
} finally {
  if ($saved -ne $null) {
    try { $o = $w.Options; $o.InsertedTextColor = $saved[0]; $o.InsertedTextMark = $saved[1]; $o.DeletedTextColor = $saved[2]; $o.DeletedTextMark = $saved[3] } catch {}
  }
  try { $w.Quit() } catch {}
  try { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue } catch {}
}
