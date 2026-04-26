param(
    [switch]$EnableOffice
)

$ErrorActionPreference = "Stop"

function New-SafeOutName {
    param(
        [string]$FullPath,
        [string]$BaseName
    )
    $hash = $null
    try {
        $hash = (Get-FileHash -Algorithm SHA1 -Path $FullPath).Hash.Substring(0, 10).ToLower()
    } catch {
        $hash = [guid]::NewGuid().ToString("N").Substring(0, 10).ToLower()
    }
    $safeBase = $BaseName
    $safeBase = $safeBase -replace '[\\/:*?"<>|]', '_'
    $safeBase = $safeBase -replace '\s+', ' '
    $safeBase = $safeBase.Trim()
    if ($safeBase.Length -gt 120) { $safeBase = $safeBase.Substring(0, 120).Trim() }
    return "$safeBase`_$hash.txt"
}

function Write-LogRow {
    param(
        [string]$CsvPath,
        [hashtable]$Row
    )
    $ordered = [ordered]@{
        file_name = $Row.file_name
        rel_path = $Row.rel_path
        ext = $Row.ext
        size_bytes = $Row.size_bytes
        method = $Row.method
        success = $Row.success
        output_txt = $Row.output_txt
        text_length = $Row.text_length
        word_count = $Row.word_count
        error = $Row.error
    }
    $obj = New-Object PSObject -Property $ordered
    $obj | Export-Csv -Path $CsvPath -NoTypeInformation -Append -Encoding UTF8
}

function Get-WordCount {
    param([string]$Text)
    if (-not $Text) { return 0 }
    $t = ($Text -replace '\s+', ' ').Trim()
    if (-not $t) { return 0 }
    return ($t -split ' ').Count
}

function Extract-DocxText {
    param([string]$FilePath)
    $tempDir = Join-Path $env:TEMP ("aouribot_docx_" + [guid]::NewGuid().ToString("N"))
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($FilePath, $tempDir)
        $wordDir = Join-Path $tempDir "word"
        if (-not (Test-Path $wordDir)) { throw "word directory not found in docx" }

        $parts = New-Object System.Collections.Generic.List[string]
        $candidateParts = @(
            (Join-Path $wordDir "document.xml"),
            (Join-Path $wordDir "footnotes.xml"),
            (Join-Path $wordDir "endnotes.xml")
        )
        $candidateParts += (Get-ChildItem -Path $wordDir -Filter "header*.xml" -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
        $candidateParts += (Get-ChildItem -Path $wordDir -Filter "footer*.xml" -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)

        $allLines = New-Object System.Collections.Generic.List[string]
        $xmlRaw = ""

        foreach ($partPath in $candidateParts) {
            if (-not (Test-Path $partPath)) { continue }
            $xmlRaw = Get-Content -Raw -Encoding UTF8 -Path $partPath
            $xml = New-Object System.Xml.XmlDocument
            $xml.PreserveWhitespace = $true
            $xml.LoadXml($xmlRaw)
            $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
            $ns.AddNamespace("w", "http://schemas.openxmlformats.org/wordprocessingml/2006/main")

            $body = $xml.SelectSingleNode("/*[local-name()='document']/*[local-name()='body']")
            if (-not $body) { $body = $xml.DocumentElement }
            $children = $body.ChildNodes
            foreach ($child in $children) {
                if (-not $child -or -not $child.LocalName) { continue }
                if ($child.LocalName -eq "p") {
                    $sb = New-Object System.Text.StringBuilder
                    $nodes = $child.SelectNodes(".//w:t|.//w:tab|.//w:br", $ns)
                    foreach ($n in $nodes) {
                        if ($n.LocalName -eq "t") { [void]$sb.Append($n.InnerText) }
                        elseif ($n.LocalName -eq "tab") { [void]$sb.Append("`t") }
                        elseif ($n.LocalName -eq "br") { [void]$sb.Append("`n") }
                    }
                    $line = $sb.ToString().TrimEnd()
                    if ($line) { $allLines.Add($line) }
                } elseif ($child.LocalName -eq "tbl") {
                    $rows = $child.SelectNodes(".//w:tr", $ns)
                    foreach ($r in $rows) {
                        $cells = $r.SelectNodes(".//w:tc", $ns)
                        $cellTexts = New-Object System.Collections.Generic.List[string]
                        foreach ($c in $cells) {
                            $sbCell = New-Object System.Text.StringBuilder
                            $cnodes = $c.SelectNodes(".//w:t|.//w:tab|.//w:br", $ns)
                            foreach ($n in $cnodes) {
                                if ($n.LocalName -eq "t") { [void]$sbCell.Append($n.InnerText) }
                                elseif ($n.LocalName -eq "tab") { [void]$sbCell.Append("`t") }
                                elseif ($n.LocalName -eq "br") { [void]$sbCell.Append("`n") }
                            }
                            $ct = ($sbCell.ToString() -replace '\s+', ' ').Trim()
                            $cellTexts.Add($ct)
                        }
                        $rowText = ($cellTexts -join "`t").TrimEnd()
                        if ($rowText) { $allLines.Add($rowText) }
                    }
                }
            }
        }

        $text = ($allLines -join "`n") -replace '\u000B', "`n"
        $text = $text -replace '\r\n', "`n"
        $text = $text -replace '\n{3,}', "`n`n"
        $text = $text.Trim()
        if (-not $text -or $text.Length -lt 50) {
            throw "extracted text too short"
        }
        return $text
    } catch {
        try {
            if ($xmlRaw) {
                $t = [regex]::Matches($xmlRaw, "<w:t[^>]*>(.*?)</w:t>", [System.Text.RegularExpressions.RegexOptions]::Singleline) | ForEach-Object { $_.Groups[1].Value }
                $fallback = ($t -join " ") -replace '\s+', ' '
                $fallback = $fallback.Trim()
                if ($fallback.Length -ge 100) { return $fallback }
            }
        } catch {}
        throw $_
    } finally {
        if (Test-Path $tempDir) {
            Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
        }
    }
}

function Extract-WithWord {
    param([string]$FilePath)
    $word = $null
    try {
        $word = New-Object -ComObject Word.Application
        $word.Visible = $false
        $word.DisplayAlerts = 0
        $word.Options.ConfirmConversions = $false
        $word.Options.UpdateLinksAtOpen = $false
        $doc = $word.Documents.Open($FilePath, $false, $true)
        $text = $doc.Content.Text
        $doc.Close($false) | Out-Null
        $text = ($text -replace '\r\n', "`n").Trim()
        if (-not $text -or $text.Length -lt 50) {
            throw "extracted text too short"
        }
        return $text
    } finally {
        if ($word) {
            $word.Quit()
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
        }
    }
}

function Extract-WithExcel {
    param([string]$FilePath)
    $excel = $null
    try {
        $excel = New-Object -ComObject Excel.Application
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        $wb = $excel.Workbooks.Open($FilePath, 0, $true)
        $outLines = New-Object System.Collections.Generic.List[string]
        foreach ($ws in $wb.Worksheets) {
            $used = $ws.UsedRange
            if ($used -and $used.Rows.Count -gt 0 -and $used.Columns.Count -gt 0) {
                $values = $used.Value2
                $rowCount = $used.Rows.Count
                $colCount = $used.Columns.Count
                $outLines.Add("=== SHEET: $($ws.Name) ===")
                for ($r = 1; $r -le $rowCount; $r++) {
                    $cells = New-Object System.Collections.Generic.List[string]
                    for ($c = 1; $c -le $colCount; $c++) {
                        $v = $values[$r, $c]
                        if ($null -eq $v) { $cells.Add("") }
                        else { $cells.Add(($v.ToString() -replace '\s+', ' ').Trim()) }
                    }
                    $line = ($cells -join "`t").TrimEnd()
                    if ($line) { $outLines.Add($line) }
                }
            }
        }
        $wb.Close($false) | Out-Null
        $text = ($outLines -join "`n").Trim()
        if (-not $text -or $text.Length -lt 50) {
            throw "extracted text too short"
        }
        return $text
    } finally {
        if ($excel) {
            $excel.Quit()
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
        }
    }
}

function Assess-PdfTextLayer {
    param([string]$FilePath)
    try {
        $bytes = [System.IO.File]::ReadAllBytes($FilePath)
        $len = [Math]::Min($bytes.Length, 2000000)
        $slice = New-Object byte[] $len
        [Array]::Copy($bytes, 0, $slice, 0, $len)
        $s = [System.Text.Encoding]::Latin1.GetString($slice)
        $hasBT = ($s.IndexOf("BT") -ge 0 -and $s.IndexOf("ET") -ge 0)
        $hasFont = ($s.IndexOf("/Font") -ge 0 -or $s.IndexOf("Tf") -ge 0)
        if ($hasBT -and $hasFont) { return $true }
        return $false
    } catch {
        return $false
    }
}

function Run-ExtractionForDir {
    param(
        [string]$RootDir,
        [string]$RelLabel,
        [string]$OutDir,
        [string]$CsvPath
    )
    $files = Get-ChildItem -Path $RootDir -File | Sort-Object @{
        Expression = {
            $e = $_.Extension.ToLower()
            switch ($e) {
                ".docx" { 0 }
                ".txt" { 1 }
                ".pdf" { 2 }
                ".doc" { 3 }
                ".xlsx" { 4 }
                ".xls" { 4 }
                default { 9 }
            }
        }
    }, Name
    $i = 0
    $total = $files.Count
    foreach ($f in $files) {
        $i++
        if ($i % 25 -eq 0) {
            Write-Host "[$RelLabel] $i/$total ..."
        }
        $row = @{
            file_name = $f.Name
            rel_path = (Join-Path $RelLabel $f.Name)
            ext = $f.Extension.ToLower()
            size_bytes = $f.Length
            method = ""
            success = $false
            output_txt = ""
            text_length = 0
            word_count = 0
            error = ""
        }
        try {
            $text = $null
            switch ($row.ext) {
                ".txt" {
                    $row.method = "txt_read"
                    try {
                        $text = Get-Content -Raw -Encoding UTF8 -Path $f.FullName
                    } catch {
                        $text = Get-Content -Raw -Path $f.FullName
                    }
                }
                ".docx" {
                    $row.method = "docx_zip_xml"
                    $text = Extract-DocxText -FilePath $f.FullName
                }
                ".doc" {
                    if ($EnableOffice) {
                        $row.method = "word_com"
                        $text = Extract-WithWord -FilePath $f.FullName
                    } else {
                        $row.method = "doc_assess_only"
                        throw "Office conversion not attempted (EnableOffice not set)"
                    }
                }
                ".pdf" {
                    $hasTextLayer = Assess-PdfTextLayer -FilePath $f.FullName
                    if (-not $hasTextLayer) {
                        $row.method = "pdf_assess_ocr_needed"
                        throw "OCR required (no obvious text layer detected)"
                    }
                    if ($EnableOffice) {
                        $row.method = "word_com_pdf"
                        $text = Extract-WithWord -FilePath $f.FullName
                    } else {
                        $row.method = "pdf_text_layer_detected"
                        throw "Text layer detected, but Office extraction not attempted (EnableOffice not set)"
                    }
                }
                ".xlsx" {
                    if ($EnableOffice) {
                        $row.method = "excel_com"
                        $text = Extract-WithExcel -FilePath $f.FullName
                    } else {
                        $row.method = "excel_assess_only"
                        throw "Office conversion not attempted (EnableOffice not set)"
                    }
                }
                ".xls" {
                    if ($EnableOffice) {
                        $row.method = "excel_com"
                        $text = Extract-WithExcel -FilePath $f.FullName
                    } else {
                        $row.method = "excel_assess_only"
                        throw "Office conversion not attempted (EnableOffice not set)"
                    }
                }
                default {
                    $row.method = "unsupported"
                    throw "unsupported format"
                }
            }
            if ($text -is [System.Array]) { $text = ($text -join "`n") }
            $text = [string]$text
            $text = ($text -replace '\r\n', "`n").Trim()
            if (-not $text -or $text.Length -lt 50) {
                throw "extracted text too short"
            }
            $outName = New-SafeOutName -FullPath $f.FullName -BaseName $f.BaseName
            $outPath = Join-Path $OutDir $outName
            $text | Out-File -FilePath $outPath -Encoding UTF8
            $row.success = $true
            $row.output_txt = $outName
            $row.text_length = $text.Length
            $row.word_count = Get-WordCount -Text $text
        } catch {
            $row.success = $false
            $row.error = $_.Exception.Message
        }
        Write-LogRow -CsvPath $CsvPath -Row $row
    }
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$outDir = Join-Path $PSScriptRoot "02_extracted_texts"
if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$csvPath = Join-Path $PSScriptRoot "02_extraction_log.csv"
if (Test-Path $csvPath) { Remove-Item -Force $csvPath }

Run-ExtractionForDir -RootDir (Join-Path $repoRoot "docs\\Contract") -RelLabel "docs/Contract" -OutDir $outDir -CsvPath $csvPath
Run-ExtractionForDir -RootDir (Join-Path $repoRoot "docs\\Standard Contract") -RelLabel "docs/Standard Contract" -OutDir $outDir -CsvPath $csvPath

