package connect

import (
	"context"
)

func (s *Service) SyncOnce(ctx context.Context) error {
	remoteHash, err := s.GetRemoteHead(ctx)
	if err != nil {
		return err
	}

	bundleFile, targetHash, err := s.CreateGitBundle(remoteHash)
	if err != nil {
		return err
	}

	err = s.SendBundle(ctx, bundleFile, targetHash)
	if err != nil {
		return err
	}

	return nil
}
