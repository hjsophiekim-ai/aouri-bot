# Enhanced Contract Text Extraction Script
# Follows proper methodology with state classification and detailed logging

function Write-ExtractionLog {
    param(
        [string]$FileName,
        [string]$FileType,
        [string]$Method,
        [bool]$Success,
        [int]$TextLength,
        [int]$WordCount,
        [string]$Language,
        [string]$Quality,
        [string]$State,
        [string]$ErrorDetails,
        [double]$ProcessingTime,
        [string]$ConfidenceLevel
    )
    
    $logEntry = "$FileName,$FileType,$Method,$Success,$TextLength,$WordCount,$Language,$Quality,$State,$ErrorDetails,$ProcessingTime,$ConfidenceLevel"
    Add-Content -Path "enhanced_extraction_log.csv" -Value $logEntry
}

function Assess-TextQuality {
    param([string]$Text)
    
    $quality = @{
        Score = 0
        Level = ""
        Issues = @()
        Recommendations = @()
    }
    
    if ($Text.Length -lt 100) {
        $quality.Issues += "Very short text"
    } elseif ($Text.Length -lt 500) {
        $quality.Score += 1
    } elseif ($Text.Length -lt 2000) {
        $quality.Score += 2
    } else {
        $quality.Score += 3
    }
    
    # Language mixture assessment
    $koreanRatio = ([regex]::Matches($Text, '[\uAC00-\uD7AF]').Count) / $Text.Length
    $englishRatio = ([regex]::Matches($Text, '[a-zA-Z]').Count) / $Text.Length
    
    if ($koreanRatio + $englishRatio -lt 0.3) {
        $quality.Issues += "Low text content ratio"
        $quality.Score -= 1
    }
    
    # XML artifacts assessment
    $xmlArtifacts = [regex]::Matches($Text, '<[^>]+>').Count
    if ($xmlArtifacts -gt 10) {
        $quality.Issues += "High XML artifact count"
        $quality.Score -= 1
    }
    
    if ($quality.Score -ge 3) {
        $quality.Level = "HIGH"
    } elseif ($quality.Score -ge 1) {
        $quality.Level = "MEDIUM"
    } else {
        $quality.Level = "LOW"
    }
    
    return $quality
}

function Extract-DocxTextEnhanced {
    param([string]$FilePath, [string]$OutputPath)
    
    $startTime = Get-Date
    $result = @{
        Success = $false
        Method = "Enhanced XML Parsing"
        TextLength = 0
        WordCount = 0
        Language = ""
        Quality = ""
        Error = ""
        State = "UNCONFIRMED"
        ConfidenceLevel = ""
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
        
        # Validate document.xml
        $docXmlPath = Join-Path $tempDir "word\document.xml"
        if (-not (Test-Path $docXmlPath)) {
            $result.Error = "document.xml not found in DOCX structure"
            $result.State = "FAILED"
            Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            return $result
        }
        
        # Parse XML with error handling
        try {
            $xmlContent = Get-Content $docXmlPath -Raw -Encoding UTF8
            $xmlDoc = [xml]$xmlContent
        } catch {
            $result.Error = "XML parsing failed: $($_.Exception.Message)"
            $result.State = "FAILED"
            Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            return $result
        }
        
        # Extract text from <w:t> tags
        $textElements = $xmlDoc.SelectNodes("//w:t", $xmlDoc.NameTable)
        $extractedText = @()
        
        foreach ($element in $textElements) {
            if ($element.InnerText.Trim()) {
                $extractedText += $element.InnerText.Trim()
            }
        }
        
        # Clean text
        $cleanText = $extractedText -join " "
        $cleanText = $cleanText -replace '\s+', ' '
        $cleanText = $cleanText -replace '\n\s*\n', "`n`n"
        
        # Quality assessment
        $qualityAssessment = Assess-TextQuality -Text $cleanText
        $result.Quality = $qualityAssessment.Level
        
        # State determination
        if ($cleanText.Length -gt 100 -and $qualityAssessment.Level -in @("MEDIUM", "HIGH")) {
            $result.State = "CONFIRMED"
            $result.ConfidenceLevel = "HIGH"
        } elseif ($cleanText.Length -gt 50) {
            $result.State = "UNCONFIRMED"
            $result.ConfidenceLevel = "MEDIUM"
        } else {
            $result.State = "FAILED"
            $result.ConfidenceLevel = "LOW"
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
        if ($result.State -ne "FAILED") {
            $cleanText | Out-File -FilePath $OutputPath -Encoding UTF8
            $result.Success = $true
            $result.TextLength = $cleanText.Length
            $result.WordCount = ($cleanText -split '\s+').Count
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
    $processingTime = ($endTime - $startTime).TotalSeconds
    
    # Write to log
    Write-ExtractionLog -FileName (Split-Path $FilePath -Leaf) `
                       -FileType "docx" `
                       -Method $result.Method `
                       -Success $result.Success `
                       -TextLength $result.TextLength `
                       -WordCount $result.WordCount `
                       -Language $result.Language `
                       -Quality $result.Quality `
                       -State $result.State `
                       -ErrorDetails $result.Error `
                       -ProcessingTime $processingTime `
                       -ConfidenceLevel $result.ConfidenceLevel
    
    return $result
}

function Assess-PdfExtraction {
    param([string]$FilePath)
    
    $assessment = @{
        NeedsOCR = $false
        HasTextLayer = $false
        Confidence = 0
        RecommendedTool = ""
        EstimatedQuality = ""
        State = "UNCONFIRMED"
    }
    
    try {
        # Check file size
        $fileInfo = Get-Item $FilePath
        $sizeMB = $fileInfo.Length / 1MB
        
        if ($sizeMB -gt 5) {
            $assessment.NeedsOCR = $true
            $assessment.RecommendedTool = "Tesseract OCR"
            $assessment.EstimatedQuality = "MEDIUM"
            $assessment.Confidence = 0.7
            $assessment.State = "NEEDS_OCR"
        }
        
        # Try to detect text layer (basic check)
        try {
            $pdfReader = New-Object -ComObject AcroPDF.Pdf.1
            if ($pdfReader) {
                $assessment.HasTextLayer = $true
                $assessment.State = "TEXT_LAYER_DETECTED"
                $assessment.Confidence = 0.8
            }
        } catch {
            $assessment.NeedsOCR = $true
            $assessment.State = "OCR_REQUIRED"
            $assessment.Confidence = 0.6
        }
        
    } catch {
        $assessment.Confidence = 0.3
        $assessment.State = "FAILED"
    }
    
    return $assessment
}

function Assess-HwpConversion {
    param([string]$FilePath)
    
    $assessment = @{
        Convertible = $false
        Method = ""
        RequiredTools = ""
        ExpectedQuality = ""
        Confidence = 0
        State = "UNCONFIRMED"
    }
    
    try {
        $bytes = [System.IO.File]::ReadAllBytes($FilePath)
        if ($bytes.Length -ge 4) {
            $signature = [System.Text.Encoding]::ASCII.GetString($bytes[0..3])
            
            if ($signature -eq "HWPX") {
                $assessment.Convertible = $true
                $assessment.Method = "HWPX ZIP Extraction"
                $assessment.RequiredTools = "ZIP extraction + XML parsing"
                $assessment.ExpectedQuality = "HIGH"
                $assessment.Confidence = 0.9
                $assessment.State = "CONVERTIBLE"
            } elseif ($signature -eq "HWP") {
                $assessment.Convertible = $true
                $assessment.Method = "HWP Viewer API"
                $assessment.RequiredTools = "Hancom Office HWP Viewer"
                $assessment.ExpectedQuality = "HIGH"
                $assessment.Confidence = 0.8
                $assessment.State = "CONVERTIBLE"
            } else {
                $assessment.Convertible = $false
                $assessment.State = "UNKNOWN_FORMAT"
                $assessment.Confidence = 0.2
            }
        }
    } catch {
        $assessment.Confidence = 0.1
        $assessment.State = "FAILED"
    }
    
    return $assessment
}

# Main execution
Write-Host "Starting Enhanced Contract Text Extraction..."

# Initialize log
"FileName,FileType,Method,Success,TextLength,WordCount,Language,Quality,State,ErrorDetails,ProcessingTime,ConfidenceLevel" | Out-File -FilePath "enhanced_extraction_log.csv"

# Get all contract files
$contractFiles = Get-ChildItem -Path "..\Contract" -File
$processedCount = 0
$successCount = 0

foreach ($file in $contractFiles) {
    $processedCount++
    Write-Host "Processing [$processedCount/$($contractFiles.Count)]: $($file.Name)"
    
    $extension = $file.Extension.ToLower()
    $baseName = $file.BaseName
    $outputFile = "extracted_$baseName.txt"
    
    switch ($extension) {
        ".docx" {
            $result = Extract-DocxTextEnhanced -FilePath $file.FullName -OutputPath $outputFile
            if ($result.Success) { $successCount++ }
            Write-Host "  Result: $($result.State) | Quality: $($result.Quality) | Length: $($result.TextLength)"
        }
        ".pdf" {
            $assessment = Assess-PdfExtraction -FilePath $file.FullName
            Write-Host "  Assessment: $($assessment.State) | Needs OCR: $($assessment.NeedsOCR)"
            # Log PDF assessment
            Write-ExtractionLog -FileName $file.Name `
                           -FileType "pdf" `
                           -Method "Assessment Only" `
                           -Success $false `
                           -TextLength 0 `
                           -WordCount 0 `
                           -Language "" `
                           -Quality "" `
                           -State $assessment.State `
                           -ErrorDetails "Assessment: $($assessment.State)" `
                           -ProcessingTime 0 `
                           -ConfidenceLevel $assessment.Confidence
        }
        ".hwp" {
            $assessment = Assess-HwpConversion -FilePath $file.FullName
            Write-Host "  Assessment: $($assessment.State) | Convertible: $($assessment.Convertible)"
            # Log HWP assessment
            Write-ExtractionLog -FileName $file.Name `
                           -FileType "hwp" `
                           -Method "Assessment Only" `
                           -Success $false `
                           -TextLength 0 `
                           -WordCount 0 `
                           -Language "" `
                           -Quality "" `
                           -State $assessment.State `
                           -ErrorDetails "Assessment: $($assessment.State)" `
                           -ProcessingTime 0 `
                           -ConfidenceLevel $assessment.Confidence
        }
        default {
            Write-Host "  Skipping unsupported format: $extension"
        }
    }
}

Write-Host "`nExtraction Complete!"
Write-Host "Files Processed: $processedCount"
Write-Host "Successful Extractions: $successCount"
Write-Host "Success Rate: $([math]::Round(($successCount / $processedCount) * 100, 2))%"
Write-Host "Log saved to: enhanced_extraction_log.csv"
