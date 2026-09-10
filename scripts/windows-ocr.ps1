param(
  [Parameter(Mandatory = $true)][string]$InputList,
  [Parameter(Mandatory = $true)][string]$Output
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

function Await-Result($Operation, [Type]$ResultType) {
  $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
      $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1
    } |
    Select-Object -First 1
  $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
  $task.Wait()
  return $task.Result
}

$language = New-Object Windows.Globalization.Language 'ko'
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if (-not $engine) {
  throw 'Windows Korean OCR is not available.'
}

$pages = foreach ($imagePath in Get-Content -LiteralPath $InputList -Encoding UTF8) {
  if (-not $imagePath) { continue }
  $fullPath = [System.IO.Path]::GetFullPath($imagePath)
  $file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($fullPath)) ([Windows.Storage.StorageFile])
  $stream = Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $result = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

  $lines = foreach ($line in $result.Lines) {
    $words = foreach ($word in $line.Words) {
      [PSCustomObject]@{
        text = $word.Text
        x = $word.BoundingRect.X
        y = $word.BoundingRect.Y
        width = $word.BoundingRect.Width
        height = $word.BoundingRect.Height
      }
    }
    [PSCustomObject]@{
      text = $line.Text
      words = @($words)
    }
  }

  [PSCustomObject]@{
    path = $fullPath
    width = $bitmap.PixelWidth
    height = $bitmap.PixelHeight
    text = $result.Text
    lines = @($lines)
  }

  $stream.Dispose()
  $bitmap.Dispose()
}

[PSCustomObject]@{ pages = @($pages) } |
  ConvertTo-Json -Depth 7 -Compress |
  Set-Content -LiteralPath $Output -Encoding UTF8
