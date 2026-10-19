module Main (main) where

import Distribution.Package
import Distribution.PackageDescription
import Distribution.Simple.PackageDescription ( readGenericPackageDescription )
import Distribution.Pretty                    ( prettyShow )
import Distribution.Simple.Utils
import Distribution.Verbosity

main :: IO ()
main = do Right fp <- findPackageDesc "."
          pd <- readGenericPackageDescription normal fp
          putStr $ prettyShow $ pkgVersion $ package $ packageDescription pd
