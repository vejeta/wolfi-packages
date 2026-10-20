#use "topfind";;
#require "opam-file-format";;

let name = "topkg"

let parse filename =
  let ic = open_in filename in
  let lexbuf = Lexing.from_channel ic in
  let r = OpamBaseParser.main OpamLexer.token lexbuf filename in
  close_in ic;
  r

let output_endline oc x =
  output_string oc x;
  output_string oc "\n"

let print filename xs =
  let oc =
    open_out_gen [ Open_wronly; Open_trunc; Open_creat ] 0o755 filename
  in
  output_endline oc "#!/bin/sh";
  List.iter (fun (_, x) -> output_endline oc x) xs;
  close_out oc

let native, bytecode =
  (parse @@ name ^ ".install").file_contents
  |> List.map (fun (x : OpamParserTypes.FullPos.opamfile_item) ->
         match x.pelem with
         | Variable (k, v) ->
             ( k.pelem,
               match v.pelem with
               | List xs ->
                   xs.pelem
                   |> List.map (fun (x : OpamParserTypes.FullPos.value) ->
                          match x.pelem with
                          | Option (src, dst) ->
                              let src =
                                match src.pelem with
                                | String x -> x
                                | _ -> failwith "src not string"
                              in
                              let dst =
                                match dst.pelem with
                                | [ { pelem = String x; _ } ] -> x
                                | _ -> failwith "dst not string"
                              in
                              (src, dst)
                          | _ -> failwith "not option")
               | _ -> failwith "not list" )
         | _ -> failwith "not variable")
  |> List.map (fun (k, v) ->
         let dest =
           match k with
           | "bin" -> "debian/tmp/usr/bin"
           | "doc" -> "debian/tmp/usr/doc/" ^ name
           | "lib" -> "debian/tmp$OCAML_STDLIB_DIR/" ^ name
           | _ -> failwith "unexpected variable"
         in
         List.map (fun (x, y) -> (x, Filename.concat dest y)) v)
  |> List.flatten
  |> List.map (fun (src, dst) ->
         let is_exe x =
           match Filename.extension x with
           | ".byte" | ".native" -> true
           | _ -> false
         in
         if is_exe src then
           let src = Filename.chop_extension src in
           [
             (true, Printf.sprintf "install -D --mode 755 %s.native %s" src dst);
             ( false,
               Printf.sprintf
                 "if [ -f %s.byte ]; then install -D --mode 755 %s.byte %s; fi"
                 src src dst );
           ]
         else
           let is_native x =
             match Filename.extension x with
             | ".a" | ".cmx" | ".cmxa" | ".cmxs" -> true
             | _ -> false
           in
           [
             ( is_native dst,
               if String.starts_with ~prefix:"?" src then
                 let src = String.sub src 1 (String.length src - 1) in
                 Printf.sprintf
                   "if [ -f %s ]; then install --mode 644 %s %s; fi" src src dst
               else Printf.sprintf "install -D --mode 644 %s %s" src dst );
           ])
  |> List.flatten |> List.partition fst

let () = print "debian/install_bytecode.sh" bytecode
let () = print "debian/install_native.sh" native
