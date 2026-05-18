import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)

    // Register our native asset-copy bridge. We use FileManager.copyItem
    // (one atomic kernel call) instead of stream-based copies because the
    // 3.2 GB GGUF triggers silent OutputStream failures on iOS — the bytes
    // are reported as written but never land on disk.
    let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "HealthWayfinderAssetCopy")!
    let channel = FlutterMethodChannel(
      name: "health_wayfinder/asset_copy",
      binaryMessenger: registrar.messenger()
    )
    channel.setMethodCallHandler { (call, result) in
      guard call.method == "copyAsset" else {
        result(FlutterMethodNotImplemented)
        return
      }
      guard let args = call.arguments as? [String: Any],
            let assetKey = args["assetKey"] as? String,
            let targetPath = args["targetPath"] as? String else {
        result(FlutterError(code: "BAD_ARGS",
                            message: "Need assetKey + targetPath",
                            details: nil))
        return
      }
      let bundleKey = FlutterDartProject.lookupKey(forAsset: assetKey)
      guard let sourcePath = Bundle.main.path(forResource: bundleKey, ofType: nil) else {
        result(FlutterError(code: "NOT_FOUND",
                            message: "Asset \(assetKey) not in bundle (key: \(bundleKey))",
                            details: nil))
        return
      }
      do {
        let fm = FileManager.default
        let dir = (targetPath as NSString).deletingLastPathComponent
        try fm.createDirectory(atPath: dir, withIntermediateDirectories: true)
        if fm.fileExists(atPath: targetPath) {
          try fm.removeItem(atPath: targetPath)
        }
        try fm.copyItem(atPath: sourcePath, toPath: targetPath)
        let attrs = try fm.attributesOfItem(atPath: targetPath)
        let size = (attrs[.size] as? NSNumber)?.int64Value ?? 0
        result(["ok": true, "size": size])
      } catch {
        result(FlutterError(code: "COPY_FAILED",
                            message: error.localizedDescription,
                            details: nil))
      }
    }
  }
}
