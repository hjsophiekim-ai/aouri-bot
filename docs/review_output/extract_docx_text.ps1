# DOCX Text Extraction Script
# Extracts clean text from DOCX files by parsing XML structure

function Extract-DocxText {
    param(
        [string]$FilePath,
        [string]$OutputPath
    )
    
    try {
        # Create temporary extraction folder
        $tempDir = "temp_extract_$(Get-Random)"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
        
        # Extract DOCX as ZIP
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($FilePath, $tempDir)
        
        # Read document.xml
        $docXmlPath = Join-Path $tempDir "word\document.xml"
        if (Test-Path $docXmlPath) {
            $xmlContent = Get-Content $docXmlPath -Raw
            $xmlDoc = [xml]$xmlContent
            
            # Extract text from <w:t> tags
            $textElements = $xmlDoc.SelectNodes("//w:t")
            $extractedText = @()
            
            foreach ($element in $textElements) {
                if ($element.InnerText.Trim()) {
                    $extractedText += $element.InnerText.Trim()
                }
            }
            
            # Clean and format text
            $cleanText = $extractedText -join " "
            $cleanText = $cleanText -replace '\s+', ' '
            $cleanText = $cleanText -replace '\n\s*\n', "`n`n"
            
            # Save to output file
            $cleanText | Out-File -FilePath $OutputPath -Encoding UTF8
            
            # Cleanup
            Remove-Item -Recurse -Force $tempDir
            
            return @{
                Success = $true
                TextLength = $cleanText.Length
                WordCount = ($cleanText -split '\s+').Count
            }
        } else {
            Remove-Item -Recurse -Force $tempDir
            return @{
                Success = $false
                Error = "document.xml not found"
            }
        }
    } catch {
        if (Test-Path $tempDir) {
            Remove-Item -Recurse -Force $tempDir
        }
        return @{
            Success = $false
            Error = $_.Exception.Message
        }
    }
}

# Main execution
$contractFolder = "..\Contract"
$outputFolder = "extracted_texts"
$logFile = "extraction_log.csv"

# Create output folder
New-Item -ItemType Directory -Path $outputFolder -Force | Out-Null

# Initialize log
"FileName,Status,TextLength,WordCount,Error" | Out-File -FilePath $logFile

# Get all DOCX files
$docxFiles = Get-ChildItem -Path $contractFolder -Filter "*.docx"

Write-Host "Found $($docxFiles.Count) DOCX files to process..."

foreach ($file in $docxFiles) {
    Write-Host "Processing: $($file.Name)"
    
    $outputFile = Join-Path $outputFolder "$($file.BaseName).txt"
    $result = Extract-DocxText -FilePath $file.FullName -OutputPath $outputFile
    
    if ($result.Success) {
        Write-Host "  SUCCESS: $($result.TextLength) chars, $($result.WordCount) words"
        "$($file.Name),SUCCESS,$($result.TextLength),$($result.WordCount)," | Out-File -FilePath $logFile -Append
    } else {
        Write-Host "  FAILED: $($result.Error)"
        "$($file.Name),FAILED,0,0,$($result.Error)" | Out-File -FilePath $logFile -Append
    }
}

Write-Host "Extraction complete. Check $outputFolder for extracted texts and $logFile for results."
