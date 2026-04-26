# Advanced Text Extraction Methodology for Contract Analysis

## Extraction Strategy Overview

### Core Principles
1. **Format-Specific Extraction**: Use appropriate methods for each file type
2. **Quality Logging**: Detailed failure reasons and success metrics
3. **State Classification**: Clear distinction between "Estimate", "Confirmed", "Unconfirmed"
4. **No Statistical Assumption**: Frequency and risk assessments only from actual extracted text

## File Format Extraction Methods

### 1. .docx Files - ZIP Structure Method

#### Primary Method: XML Parsing
```powershell
# Advanced DOCX Extraction Script
function Extract-DocxTextAdvanced {
    param([string]$FilePath, [string]$OutputPath)
    
    $result = @{
        Success = $false
        Method = "XML Parsing"
        TextLength = 0
        WordCount = 0
        Language = ""
        Quality = ""
        Error = ""
        State = "UNCONFIRMED"
    }
    
    try {
        # Step 1: Validate DOCX structure
        if (-not (Test-Path $FilePath)) {
            $result.Error = "File not found"
            return $result
        }
        
        # Step 2: Extract as ZIP
        $tempDir = "temp_extract_$(Get-Random)"
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($FilePath, $tempDir)
        
        # Step 3: Validate document.xml exists
        $docXmlPath = Join-Path $tempDir "word\document.xml"
        if (-not (Test-Path $docXmlPath)) {
            $result.Error = "document.xml not found in DOCX structure"
            Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            return $result
        }
        
        # Step 4: Parse XML with error handling
        try {
            $xmlContent = Get-Content $docXmlPath -Raw -Encoding UTF8
            $xmlDoc = [xml]$xmlContent
        } catch {
            $result.Error = "XML parsing failed: $($_.Exception.Message)"
            Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            return $result
        }
        
        # Step 5: Extract text from <w:t> tags with namespace handling
        $textElements = $xmlDoc.SelectNodes("//w:t", $xmlDoc.NameTable)
        $extractedText = @()
        
        foreach ($element in $textElements) {
            if ($element.InnerText.Trim()) {
                $extractedText += $element.InnerText.Trim()
            }
        }
        
        # Step 6: Clean and validate text
        $cleanText = $extractedText -join " "
        $cleanText = $cleanText -replace '\s+', ' '
        $cleanText = $cleanText -replace '\n\s*\n', "`n`n"
        
        # Step 7: Quality assessment
        if ($cleanText.Length -lt 100) {
            $result.Quality = "LOW"
            $result.State = "UNCONFIRMED"
        } elseif ($cleanText.Length -lt 1000) {
            $result.Quality = "MEDIUM"
            $result.State = "CONFIRMED"
        } else {
            $result.Quality = "HIGH"
            $result.State = "CONFIRMED"
        }
        
        # Step 8: Language detection
        $koreanChars = [regex]::Matches($cleanText, '[\uAC00-\uD7AF]').Count
        $englishChars = [regex]::Matches($cleanText, '[a-zA-Z]').Count
        
        if ($koreanChars -gt $englishChars) {
            $result.Language = "Korean"
        } elseif ($englishChars -gt $koreanChars) {
            $result.Language = "English"
        } else {
            $result.Language = "Mixed"
        }
        
        # Step 9: Save results
        $cleanText | Out-File -FilePath $OutputPath -Encoding UTF8
        $result.Success = $true
        $result.TextLength = $cleanText.Length
        $result.WordCount = ($cleanText -split '\s+').Count
        
        # Step 10: Cleanup
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
        
        return $result
        
    } catch {
        if (Test-Path $tempDir) {
            Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
        }
        $result.Error = "General extraction error: $($_.Exception.Message)"
        return $result
    }
}
```

#### Fallback Methods
1. **COM Object Method**: Use Word.Application if available
2. **Third-party Libraries**: DocumentFormat.OpenXml if PowerShell modules available
3. **Manual Extraction**: For corrupted files, attempt partial extraction

### 2. .pdf Files - Text Layer Detection

#### Primary Method: Text Layer Extraction
```powershell
function Extract-PdfTextAdvanced {
    param([string]$FilePath, [string]$OutputPath)
    
    $result = @{
        Success = $false
        Method = ""
        TextLength = 0
        WordCount = 0
        HasTextLayer = $false
        NeedsOCR = $false
        Quality = ""
        Error = ""
        State = "UNCONFIRMED"
    }
    
    try {
        # Step 1: Check if PDF has text layer
        $pdfReader = New-Object -ComObject AcroPDF.Pdf.1
        if ($pdfReader) {
            $pdfReader.LoadFile($FilePath)
            $hasText = $pdfReader.GetNumPages() -gt 0
            
            if ($hasText) {
                # Try text extraction
                $text = ""
                for ($i = 0; $i -lt $pdfReader.GetNumPages(); $i++) {
                    $pdfReader.setCurrentPage($i)
                    $text += $pdfReader.GetPageText()
                }
                
                if ($text.Length -gt 100) {
                    $result.Success = $true
                    $result.Method = "Acrobat COM"
                    $result.HasTextLayer = $true
                    $result.NeedsOCR = $false
                    $result.TextLength = $text.Length
                    $result.WordCount = ($text -split '\s+').Count
                    $result.State = "CONFIRMED"
                    $result.Quality = "HIGH"
                    
                    $text | Out-File -FilePath $OutputPath -Encoding UTF8
                } else {
                    $result.NeedsOCR = $true
                    $result.Error = "PDF has text layer but extraction failed"
                }
            } else {
                $result.NeedsOCR = $true
                $result.Error = "PDF appears to be scanned/image-based"
            }
        } else {
            $result.Error = "Acrobat COM not available"
        }
        
    } catch {
        $result.Error = "PDF extraction error: $($_.Exception.Message)"
    }
    
    return $result
}
```

#### OCR Assessment for Scanned PDFs
```powershell
function Assess-PdfOCRNeeds {
    param([string]$FilePath)
    
    $assessment = @{
        NeedsOCR = $false
        Confidence = 0
        RecommendedTool = ""
        EstimatedQuality = ""
    }
    
    # Check if PDF is scanned
    try {
        # Method 1: Check file size vs expected text content
        $fileInfo = Get-Item $FilePath
        $sizeMB = $fileInfo.Length / 1MB
        
        if ($sizeMB -gt 5) {
            # Large PDF likely contains images
            $assessment.NeedsOCR = $true
            $assessment.RecommendedTool = "Tesseract OCR"
            $assessment.EstimatedQuality = "MEDIUM"
            $assessment.Confidence = 0.7
        }
        
        # Method 2: Try to extract a sample of text
        $sampleText = Extract-PdfTextSample -FilePath $FilePath -SamplePages 2
        if ($sampleText.Length -lt 50) {
            $assessment.NeedsOCR = $true
            $assessment.Confidence = 0.8
        }
        
    } catch {
        $assessment.Confidence = 0.3
    }
    
    return $assessment
}
```

### 3. .hwp/.hwpx Files - Korean Word Processor

#### Conversion Assessment
```powershell
function Assess-HwpConversion {
    param([string]$FilePath)
    
    $assessment = @{
        Convertible = $false
        Method = ""
        RequiredTools = ""
        ExpectedQuality = ""
        Confidence = 0
    }
    
    try {
        # Check file signature
        $bytes = [System.IO.File]::ReadAllBytes($FilePath)
        $signature = [System.Text.Encoding]::ASCII.GetString($bytes[0..4])
        
        if ($signature -eq "HWPDocument") {
            $assessment.Convertible = $true
            $assessment.Method = "HWP Viewer API"
            $assessment.RequiredTools = "Hancom Office HWP Viewer"
            $assessment.ExpectedQuality = "HIGH"
            $assessment.Confidence = 0.8
        } elseif ($signature -eq "HWPX") {
            $assessment.Convertible = $true
            $assessment.Method = "HWPX ZIP Extraction"
            $assessment.RequiredTools = "ZIP extraction + XML parsing"
            $assessment.ExpectedQuality = "HIGH"
            $assessment.Confidence = 0.9
        } else {
            $assessment.Convertible = $false
            $assessment.Method = "Unknown format"
            $assessment.Confidence = 0.2
        }
        
    } catch {
        $assessment.Confidence = 0.1
    }
    
    return $assessment
}
```

### 4. .doc Files - Legacy Word Format

#### Conversion Method
```powershell
function Convert-DocToDocx {
    param([string]$FilePath, [string]$OutputPath)
    
    $result = @{
        Success = $false
        Method = ""
        ConvertedPath = ""
        Error = ""
    }
    
    try {
        # Method 1: Word COM automation
        $wordApp = New-Object -ComObject Word.Application
        $wordApp.Visible = $false
        
        $doc = $wordApp.Documents.Open($FilePath)
        $doc.SaveAs([ref]$OutputPath, [ref]16) # 16 = wdFormatXMLDocument
        $doc.Close()
        $wordApp.Quit()
        
        $result.Success = $true
        $result.Method = "Word COM Automation"
        $result.ConvertedPath = $OutputPath
        
    } catch {
        $result.Error = "Word conversion failed: $($_.Exception.Message)"
        
        # Method 2: Try LibreOffice if available
        try {
            $libreOffice = "soffice --headless --convert-to docx --outdir $OutputDir $FilePath"
            $result.Method = "LibreOffice Conversion"
        } catch {
            $result.Error = "Both Word and LibreOffice conversion failed"
        }
    }
    
    return $result
}
```

## Comprehensive Logging System

### Extraction Log Structure
```csv
FileName,FileType,ExtractionMethod,Success,TextLength,WordCount,Language,Quality,State,ErrorDetails,ProcessingTime,ConfidenceLevel
```

### State Classification Rules
- **CONFIRMED**: Text successfully extracted, length > 100 characters, readable content
- **UNCONFIRMED**: Text extracted but quality low (< 100 chars) or contains significant artifacts
- **ESTIMATE**: Based on filename analysis only, no text extracted
- **FAILED**: Extraction attempted but failed with specific error

### Quality Assessment Metrics
```powershell
function Assess-TextQuality {
    param([string]$Text)
    
    $quality = @{
        Score = 0
        Level = ""
        Issues = @()
        Recommendations = @()
    }
    
    # Length assessment
    if ($Text.Length -lt 100) {
        $quality.Score += 0
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
        $quality.Recommendations += "Improve XML cleaning"
    }
    
    # Determine quality level
    if ($quality.Score -ge 3) {
        $quality.Level = "HIGH"
    } elseif ($quality.Score -ge 1) {
        $quality.Level = "MEDIUM"
    } else {
        $quality.Level = "LOW"
    }
    
    return $quality
}
```

## Implementation Plan

### Phase 1: Enhanced .docx Extraction
1. Implement advanced XML parsing with error handling
2. Add quality assessment and language detection
3. Create detailed logging system
4. Test on known good and problematic files

### Phase 2: PDF Processing
1. Implement text layer detection
2. Add OCR assessment capabilities
3. Create fallback methods for different PDF types
4. Test on sample PDF files

### Phase 3: Format Support Expansion
1. Evaluate .hwp/.hwpx conversion possibilities
2. Implement .doc to .docx conversion
3. Add Excel file processing for contract data
4. Create unified extraction interface

### Phase 4: Quality Assurance
1. Validate extraction results against manual samples
2. Create quality metrics and benchmarks
3. Implement automated quality checks
4. Generate comprehensive extraction reports

## Success Metrics

### Extraction Success Rates by Format
- .docx: Target 80%+ (currently 3.7%)
- .pdf: Target 60%+ (currently 0%)
- .doc: Target 50%+ (currently 0%)
- .hwp: Target 30%+ (currently 0%)

### Quality Metrics
- High Quality Extracted Text: Target 70%+ of successful extractions
- Language Detection Accuracy: Target 90%+
- Error Classification Accuracy: Target 95%+

---

*This methodology provides a comprehensive framework for reliable text extraction from various contract file formats while maintaining clear state classification and detailed logging.*
