[CmdletBinding()]
param(
    [string]$DocxPath,
    [string]$PdfPath
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($DocxPath)) {
    $DocxPath = Join-Path $PSScriptRoot 'output\Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.docx'
}
if ([string]::IsNullOrWhiteSpace($PdfPath)) {
    $PdfPath = Join-Path $PSScriptRoot 'output\Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pdf'
}
$docx = [System.IO.Path]::GetFullPath($DocxPath)
$pdf = [System.IO.Path]::GetFullPath($PdfPath)
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($docx, $false, $false)
    foreach ($toc in $document.TablesOfContents) { $toc.Update() }
    $document.Fields.Update() | Out-Null
    $document.Save()
    $document.ExportAsFixedFormat($pdf, 17)
    Write-Output $pdf
} finally {
    if ($null -ne $document) { $document.Close($false) }
    if ($null -ne $word) { $word.Quit() }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
