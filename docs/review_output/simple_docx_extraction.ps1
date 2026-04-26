# Simple DOCX Text Extraction Script
# Uses basic string manipulation instead of XML parsing

function Extract-DocxTextSimple {
    param([string]$FilePath, [string]$OutputPath)
    
    $startTime = Get-Date
    $result = @{
        Success = $false
        Method = "Simple String Extraction"
        TextLength = 0
        WordCount = 0
        Language = ""
        Quality = ""
        Error = ""
        State = "UNCONFIRMED"
        ConfidenceLevel = ""
        ProcessingTime = 0
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
        
        # Read XML as plain text and extract content between tags
        try {
            $xmlContent = Get-Content $docXmlPath -Raw -Encoding UTF8
            
            # Extract text from <w:t> tags using regex
            $textPattern = '<w:t[^>]*>(.*?)</w:t>'
            $matches = [regex]::Matches($xmlContent, $textPattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
            
            $extractedText = @()
            foreach ($match in $matches) {
                $textContent = $match.Groups[1].Value
                # Decode common XML entities
                $textContent = $textContent -replace '&quot;', '"'
                $textContent = $textContent -replace '&apos;', "'"
                $textContent = $textContent -replace '&lt;', '<'
                $textContent = $textContent -replace '&gt;', '>'
                $textContent = $textContent -replace '&amp;', '&'
                
                if ($textContent.Trim()) {
                    $extractedText += $textContent.Trim()
                }
            }
            
            # Also try to extract from tables
            $tablePattern = '<w:tc[^>]*>.*?<w:t[^>]*>(.*?)</w:t>.*?</w:tc>'
            $tableMatches = [regex]::Matches($xmlContent, $tablePattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
            
            foreach ($match in $tableMatches) {
                $tableText = $match.Groups[1].Value
                $tableText = $tableText -replace '&quot;', '"'
                $tableText = $tableText -replace '&apos;', "'"
                $tableText = $tableText -replace '&lt;', '<'
                $tableText = $tableText -replace '&gt;', '>'
                $tableText = $tableText -replace '&amp;', '&'
                
                if ($tableText.Trim()) {
                    $extractedText += $tableText.Trim()
                }
            }
            
            # Combine and clean text
            $cleanText = $extractedText -join " "
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
            $result.Error = "Text extraction failed: $($_.Exception.Message)"
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

# Main execution
Write-Host "Starting Simple DOCX Text Extraction..."

# Initialize results
$results = @()
$processedCount = 0
$successCount = 0

# Get only .docx files
$docxFiles = Get-ChildItem -Path "..\Contract" -Filter "*.docx"

Write-Host "Found $($docxFiles.Count) DOCX files to process..."

foreach ($file in $docxFiles) {
    $processedCount++
    Write-Host "Processing [$processedCount/$($docxFiles.Count)]: $($file.Name)"
    
    $baseName = $file.BaseName
    $outputFile = "simple_extracted_$baseName.txt"
    
    $result = Extract-DocxTextSimple -FilePath $file.FullName -OutputPath $outputFile
    
    $fileResult = @{
        FileName = $file.Name
        State = $result.State
        Method = $result.Method
        Success = $result.Success
        TextLength = $result.TextLength
        WordCount = $result.WordCount
        Language = $result.Language
        Quality = $result.Quality
        Error = $result.Error
        ProcessingTime = $result.ProcessingTime
        ConfidenceLevel = $result.ConfidenceLevel
    }
    
    $results += $fileResult
    
    if ($result.Success) { 
        $successCount++
        Write-Host "  SUCCESS: $($result.State) | Quality: $($result.Quality) | Length: $($result.TextLength)"
    } else {
        Write-Host "  FAILED: $($result.State) | Error: $($result.Error)"
    }
}

# Generate summary
$summary = @{
    TotalDocxFiles = $docxFiles.Count
    ProcessedFiles = $processedCount
    SuccessfulExtractions = $successCount
    SuccessRate = [math]::Round(($successCount / $processedCount) * 100, 2)
    Results = $results
}

# Save results
$results | ConvertTo-Json -Depth 3 | Out-File -FilePath "simple_extraction_results.json" -Encoding UTF8
$summary | ConvertTo-Json -Depth 3 | Out-File -FilePath "simple_extraction_summary.json" -Encoding UTF8

Write-Host "`nSimple DOCX Extraction Complete!"
Write-Host "DOCX Files Processed: $($summary.ProcessedFiles)"
Write-Host "Successful Extractions: $($summary.SuccessfulExtractions)"
Write-Host "Success Rate: $($summary.SuccessRate)%"
Write-Host "Results saved to: simple_extraction_results.json"
Write-Host "Summary saved to: simple_extraction_summary.json"
