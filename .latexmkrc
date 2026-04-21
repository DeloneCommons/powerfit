# Keep LaTeX outputs next to the source file even when latexmk is launched
# from the repository root or by an editor integration.
$do_cd = 1;

# Successful direct latexmk runs should leave the manuscript tree tidy.
# Keep the tracked .bbl in place, but remove the usual disposable byproducts.
sub cleanup_post_build {
  my ($root) = @_;
  for my $suffix (
    qw(aux bcf blg fdb_latexmk fls ilg ind lof log lot nlo nls out spl synctex.gz toc xdv),
    'run.xml'
  ) {
    unlink "$root.$suffix";
  }
  return 0;
}

$success_cmd = 'internal cleanup_post_build %R';
$warning_cmd = 'internal cleanup_post_build %R';
