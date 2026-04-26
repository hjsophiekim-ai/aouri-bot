# Improved DOCX Text Extraction Script
# Fixes XML namespace issues and extracts from multiple document parts

function Add-XmlNamespace {
    param([xml]$XmlDoc, [string]$Prefix, [string]$Namespace)
    
    $ns = New-Object System.Xml.XmlNamespaceManager($XmlDoc.NameTable)
    $ns.AddNamespace($Prefix, $Namespace)
    return $ns
}

function Extract-DocxTextImproved {
    param([string]$FilePath, [string]$OutputPath)
    
    $startTime = Get-Date
    $result = @{
        Success = $false
        Method = "Improved XML Parsing"
        TextLength = 0
        WordCount = 0
        Language = ""
        Quality = ""
        Error = ""
        State = "UNCONFIRMED"
        ConfidenceLevel = ""
        ProcessingTime = 0
        ExtractedParts = @()
    }
    
    try {
        # Validate file exists
        if (-not (Test-Path $FilePath)) {
            $result.Error = "File not found"
            $result.State = "FAILED"
            return $result
        }
        
        # Extract as ZIP
        $tempDir = "temp_extract_$(Get-Random)"
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($FilePath, $tempDir)
        
        # Validate document.xml exists
        $docXmlPath = Join-Path $tempDir "word\document.xml"
        if (-not (Test-Path $docXmlPath)) {
            $result.Error = "document.xml not found in DOCX structure"
            $result.State = "FAILED"
            Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            return $result
        }
        
        # Parse XML with namespace handling
        try {
            $xmlContent = Get-Content $docXmlPath -Raw -Encoding UTF8
            $xmlDoc = [xml]$xmlContent
            
            # Add namespace manager
            $ns = Add-XmlNamespace -XmlDoc $xmlDoc -Prefix "w" -Namespace "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            
            # Extract text from document body
            $bodyText = @()
            $textElements = $xmlDoc.SelectNodes("//w:t", $ns)
            
            foreach ($element in $textElements) {
                if ($element.InnerText.Trim()) {
                    $bodyText += $element.InnerText.Trim()
                }
            }
            
            $result.ExtractedParts += "Document Body: $($bodyText.Count) text elements"
            
            # Extract from headers if available
            $headerText = @()
            $headerXmlPath = Join-Path $tempDir "word\header1.xml"
            if (Test-Path $headerXmlPath) {
                try {
                    $headerXml = Get-Content $headerXmlPath -Raw -Encoding UTF8
                    $headerDoc = [xml]$headerXml
                    $headerNs = Add-XmlNamespace -XmlDoc $headerDoc -Prefix "w" -Namespace "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                    $headerElements = $headerDoc.SelectNodes("//w:t", $headerNs)
                    
                    foreach ($element in $headerElements) {
                        if ($element.InnerText.Trim()) {
                            $headerText += $element.InnerText.Trim()
                        }
                    }
                    $result.ExtractedParts += "Header1: $($headerText.Count) text elements"
                } catch {
                    $result.ExtractedParts += "Header1: Failed to parse"
                }
            }
            
            # Extract from footers if available
            $footerText = @()
            $footerXmlPath = Join-Path $tempDir "word\footer1.xml"
            if (Test-Path $footerXmlPath) {
                try {
                    $footerXml = Get-Content $footerXmlPath -Raw -Encoding UTF8
                    $footerDoc = [xml]$footerXml
                    $footerNs = Add-XmlNamespace -XmlDoc $footerDoc -Prefix "w" -Namespace "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                    $footerElements = $footerDoc.SelectNodes("//w:t", $footerNs)
                    
                    foreach ($element in $footerElements) {
                        if ($element.InnerText.Trim()) {
                            $footerText += $element.InnerText.Trim()
                        }
                    }
                    $result.ExtractedParts += "Footer1: $($footerText.Count) text elements"
                } catch {
                    $result.ExtractedParts += "Footer1: Failed to parse"
                }
            }
            
            # Extract from text boxes if available
            $textBoxText = @()
            $textBoxXmlPath = Join-Path $tempDir "word\document.xml"
            if (Test-Path $textBoxXmlPath) {
                try {
                    $textBoxElements = $xmlDoc.SelectNodes("//w:p/w:r/w:t", $ns)
                    foreach ($element in $textBoxElements) {
                        if ($element.InnerText.Trim()) {
                            $textBoxText += $element.InnerText.Trim()
                        }
                    }
                    $result.ExtractedParts += "Text Boxes: $($textBoxText.Count) text elements"
                } catch {
                    $result.ExtractedParts += "Text Boxes: Failed to parse"
                }
            }
            
            # Combine all extracted text
            $allText = $bodyText + $headerText + $footerText + $textBoxText
            $cleanText = $allText -join " "
            $cleanText = $cleanText -replace '\s+', ' '
            $cleanText = $cleanText -replace '\n\s*\n', "`n`n"
            
            # Quality assessment
            if ($cleanText.Length -lt 50) {
                $result.Quality = "VERY LOW"
                $result.State = "UNCONFIRMED"
                $result.ConfidenceLevel = "LOW"
            } elseif ($cleanText.Length -lt 200) {
                $result.Quality = "LOW"
                $result.State = "UNCONFIRMED"
                $result.ConfidenceLevel = "MEDIUM"
            } elseif ($cleanText.Length -lt 1000) {
                $result.Quality = "MEDIUM"
                $result.State = "CONFIRMED"
                $result.ConfidenceLevel = "HIGH"
            } else {
                $result.Quality = "HIGH"
                $result.State = "CONFIRMED"
                $result.ConfidenceLevel = "HIGH"
            }
            
            # Language detection
            $koreanChars = [regex]::Matches($cleanText, '[\uAC00-\uD7AF]').Count
            $englishChars = [regex]::Matches($cleanText, '[a-zA-Z]').Count
            
            if ($koreanChars -gt $englishChars) {
                $result.Language = "Korean"
            } elseif ($englishChars -gt $koreanChars) {
                $result.Language = "English"
            } else {
                $result.Language = "Mixed"
            }
            
            # Save results
            if ($result.State -eq "CONFIRMED") {
                $cleanText | Out-File -FilePath $OutputPath -Encoding UTF8
                $result.Success = $true
                $result.TextLength = $cleanText.Length
                $result.WordCount = ($cleanText -split '\s+').Count
            }
            
        } catch {
            $result.Error = "XML parsing failed: $($_.Exception.Message)"
            $result.State = "FAILED"
            $result.ConfidenceLevel = "LOW"
        }
        
        # Cleanup
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
        
    } catch {
        if (Test-Path $tempDir) {
            Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
        }
        $result.Error = "General extraction error: $($_.Exception.Message)"
        $result.State = "FAILED"
        $result.ConfidenceLevel = "LOW"
    }
    
    # Log processing time
    $endTime = Get-Date
    $result.ProcessingTime = ($endTime - $startTime).TotalSeconds
    
    return $result
}

function Assess-PdfTextLayer {
    param([string]$FilePath)
    
    $assessment = @{
        HasTextLayer = $false
        NeedsOCR = $false
        Confidence = 0
        Method = ""
        State = "UNCONFIRMED"
        Error = ""
    }
    
    try {
        # Check file size
        $fileInfo = Get-Item $FilePath
        $sizeMB = $fileInfo.Length / 1MB
        
        # Try to detect text layer using basic approach
        try {
            # Read first few bytes to check for PDF signature
            $bytes = [System.IO.File]::ReadAllBytes($FilePath)
            $signature = [System.Text.Encoding]::ASCII.GetString($bytes[0..4])
            
            if ($signature -eq "%PDF") {
                # Simple heuristic: large PDFs are more likely to be scanned
                if ($sizeMB -gt 2) {
                    $assessment.NeedsOCR = $true
                    $assessment.Confidence = 0.6
                    $assessment.State = "OCR_RECOMMENDED"
                    $assessment.Method = "Size-based heuristic"
                } else {
                    $assessment.HasTextLayer = $true
                    $assessment.Confidence = 0.4
                    $assessment.State = "TEXT_LAYER_SUSPECTED"
                    $assessment.Method = "Size-based heuristic"
                }
            } else {
                $assessment.Error = "Not a valid PDF file"
                $assessment.State = "INVALID_FORMAT"
            }
        } catch {
            $assessment.Error = "PDF analysis failed: $($_.Exception.Message)"
            $assessment.State = "FAILED"
        }
        
    } catch {
        $assessment.Error = "File access error: $($_.Exception.Message)"
        $assessment.State = "FAILED"
    }
    
    return $assessment
}

function Check-DocConversion {
    param([string]$FilePath)
    
    $assessment = @{
        Convertible = $false
        Method = ""
        RequiredTools = ""
        Confidence = 0
        State = "UNCONFIRMED"
        Error = ""
    }
    
    try {
        # Check if Word is available
        try {
            $wordApp = New-Object -ComObject Word.Application
            $wordApp.Quit()
            $assessment.Convertible = $true
            $assessment.Method = "Word COM Automation"
            $assessment.RequiredTools = "Microsoft Word"
            $assessment.Confidence = 0.8
            $assessment.State = "CONVERTIBLE"
        } catch {
            $assessment.Convertible = $false
            $assessment.Method = "Word not available"
            $assessment.RequiredTools = "Microsoft Word or LibreOffice"
            $assessment.Confidence = 0.2
            $assessment.State = "CONVERSION_NOT_AVAILABLE"
            $assessment.Error = "Word COM not available"
        }
        
    } catch {
        $assessment.Error = "Conversion check failed: $($_.Exception.Message)"
        $assessment.State = "FAILED"
    }
    
    return $assessment
}

function Check-HwpSupport {
    param([string]$FilePath)
    
    $assessment = @{
        Supported = $false
        Method = ""
        RequiredTools = ""
        Confidence = 0
        State = "UNCONFIRMED"
        Error = ""
    }
    
    try {
        $bytes = [System.IO.File]::ReadAllBytes($FilePath)
        if ($bytes.Length -ge 4) {
            $signature = [System.Text.Encoding]::ASCII.GetString($bytes[0..3])
            
            if ($signature -eq "HWPX") {
                $assessment.Supported = $true
                $assessment.Method = "HWPX ZIP Extraction"
                $assessment.RequiredTools = "ZIP extraction + XML parsing"
                $assessment.Confidence = 0.9
                $assessment.State = "SUPPORTED"
            } elseif ($signature -eq "HWP") {
                $assessment.Supported = $false
                $assessment.Method = "HWP Viewer API"
                $assessment.RequiredTools = "Hancom Office HWP Viewer"
                $assessment.Confidence = 0.3
                $assessment.State = "SUPPORTED_WITH_TOOLS"
            } else {
                $assessment.Supported = $false
                $assessment.State = "UNSUPPORTED_FORMAT"
                $assessment.Confidence = 0.1
            }
        } else {
            $assessment.State = "INVALID_FILE"
            $assessment.Confidence = 0.1
        }
        
    } catch {
        $assessment.Error = "HWP analysis failed: $($_.Exception.Message)"
        $assessment.State = "FAILED"
    }
    
    return $assessment
}

# Main execution
Write-Host "Starting Improved Contract Text Extraction..."

# Initialize results
$results = @()
$processedCount = 0
$successCount = 0

# Get all contract files
$contractFiles = Get-ChildItem -Path "..\Contract" -File

foreach ($file in $contractFiles) {
    $processedCount++
    Write-Host "Processing [$processedCount/$($contractFiles.Count)]: $($file.Name)"
    
    $extension = $file.Extension.ToLower()
    $baseName = $file.BaseName
    $outputFile = "extracted_$baseName.txt"
    
    $fileResult = @{
        FileName = $file.Name
        FileType = $extension
        State = "UNCONFIRMED"
        Method = ""
        Success = $false
        TextLength = 0
        WordCount = 0
        Language = ""
        Quality = ""
        Error = ""
        ProcessingTime = 0
        ConfidenceLevel = ""
        ExtractedParts = @()
    }
    
    switch ($extension) {
        ".docx" {
            $result = Extract-DocxTextImproved -FilePath $file.FullName -OutputPath $outputFile
            $fileResult.State = $result.State
            $fileResult.Method = $result.Method
            $fileResult.Success = $result.Success
            $fileResult.TextLength = $result.TextLength
            $fileResult.WordCount = $result.WordCount
            $fileResult.Language = $result.Language
            $fileResult.Quality = $result.Quality
            $fileResult.Error = $result.Error
            $fileResult.ProcessingTime = $result.ProcessingTime
            $fileResult.ConfidenceLevel = $result.ConfidenceLevel
            $fileResult.ExtractedParts = $result.ExtractedParts
            
            if ($result.Success) { 
                $successCount++
                Write-Host "  SUCCESS: $($result.State) | Quality: $($result.Quality) | Length: $($result.TextLength)"
            } else {
                Write-Host "  FAILED: $($result.State) | Error: $($result.Error)"
            }
        }
        ".pdf" {
            $assessment = Assess-PdfTextLayer -FilePath $file.FullName
            $fileResult.State = $assessment.State
            $fileResult.Method = $assessment.Method
            $fileResult.Error = $assessment.Error
            $fileResult.ConfidenceLevel = $assessment.Confidence.ToString()
            
            Write-Host "  PDF Assessment: $($assessment.State) | Needs OCR: $($assessment.NeedsOCR)"
        }
        ".doc" {
            $assessment = Check-DocConversion -FilePath $file.FullName
            $fileResult.State = $assessment.State
            $fileResult.Method = $assessment.Method
            $fileResult.Error = $assessment.Error
            $fileResult.ConfidenceLevel = $assessment.Confidence.ToString()
            
            Write-Host "  DOC Assessment: $($assessment.State) | Convertible: $($assessment.Convertible)"
        }
        ".hwp" {
            $assessment = Check-HwpSupport -FilePath $file.FullName
            $fileResult.State = $assessment.State
            $fileResult.Method = $assessment.Method
            $fileResult.Error = $assessment.Error
            $fileResult.ConfidenceLevel = $assessment.Confidence.ToString()
            
            Write-Host "  HWP Assessment: $($assessment.State) | Supported: $($assessment.Supported)"
        }
        default {
            $fileResult.State = "UNSUPPORTED_FORMAT"
            $fileResult.Error = "File type not supported for extraction"
            Write-Host "  Skipping unsupported format: $extension"
        }
    }
    
    $results += $fileResult
}

# Generate summary report
$summary = @{
    TotalFiles = $contractFiles.Count
    ProcessedFiles = $processedCount
    SuccessfulExtractions = $successCount
    SuccessRate = [math]::Round(($successCount / $processedCount) * 100, 2)
    ResultsByType = @{}
    FailureReasons = @{}
}

# Group results by file type
foreach ($result in $results) {
    if (-not $summary.ResultsByType.ContainsKey($result.FileType)) {
        $summary.ResultsByType[$result.FileType] = @{
            Total = 0
            Success = 0
            Failed = 0
            States = @{}
        }
    }
    
    $summary.ResultsByType[$result.FileType].Total++
    
    if ($result.Success) {
        $summary.ResultsByType[$result.FileType].Success++
    } else {
        $summary.ResultsByType[$result.FileType].Failed++
    }
    
    if (-not $summary.ResultsByType[$result.FileType].States.ContainsKey($result.State)) {
        $summary.ResultsByType[$result.FileType].States[$result.State] = 0
    }
    $summary.ResultsByType[$result.FileType].States[$result.State]++
    
    # Track failure reasons
    if ($result.Error -and $result.State -eq "FAILED") {
        $errorKey = if ($result.Error -like "*namespace*") { "XML Namespace Error" }
                   elseif ($result.Error -like "*not found*") { "File Structure Error" }
                   elseif ($result.Error -like "*parsing*") { "XML Parsing Error" }
                   else { "Other Error" }
                   
        if (-not $summary.FailureReasons.ContainsKey($errorKey)) {
            $summary.FailureReasons[$errorKey] = 0
        }
        $summary.FailureReasons[$errorKey]++
    }
}

# Save results
$results | ConvertTo-Json -Depth 3 | Out-File -FilePath "improved_extraction_results.json" -Encoding UTF8
$summary | ConvertTo-Json -Depth 3 | Out-File -FilePath "improved_extraction_summary.json" -Encoding UTF8

Write-Host "`nImproved Extraction Complete!"
Write-Host "Files Processed: $($summary.ProcessedFiles)"
Write-Host "Successful Extractions: $($summary.SuccessfulExtractions)"
Write-Host "Success Rate: $($summary.SuccessRate)%"
Write-Host "Results saved to: improved_extraction_results.json"
Write-Host "Summary saved to: improved_extraction_summary.json"
